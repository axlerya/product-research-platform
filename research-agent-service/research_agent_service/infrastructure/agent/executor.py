"""ToolExecutor — исполнение одного вызова инструмента агентом.

Диспетчеризует валидированный вызов в прикладной сервис и возвращает
``ExecutedTool``: наблюдение для LLM, доменный ToolCall, цитаты (provenance)
и деградации. Ошибки не пробрасываются в граф: некорректные аргументы →
REJECTED, отказ зависимости → ERROR + деградация — модель видит это как
обычное наблюдение и может перепланировать.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from research_agent_service.application.ports.clock import Clock
from research_agent_service.application.ports.id_generator import IdGenerator
from research_agent_service.application.services.price_analysis import (
    PriceAnalysisService,
)
from research_agent_service.application.services.product_catalog_rag import (
    ProductCatalogRagService,
)
from research_agent_service.application.services.web_search import (
    WebSearchService,
)
from research_agent_service.domain.entities.tool_call import ToolCall
from research_agent_service.domain.exceptions import InvalidQuery
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import (
    CitationType,
    ToolCallStatus,
    ToolName,
)
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ToolCallId,
)
from research_agent_service.infrastructure.agent.contracts import (
    PriceAnalysisArgs,
    ProductCatalogRagArgs,
    WebSearchArgs,
)
from research_agent_service.infrastructure.agent.observations import (
    price_observation,
    rag_observation,
    web_observation,
)

_DETAIL_MAX = 200


@dataclass(frozen=True, slots=True)
class ExecutedTool:
    """Итог одного вызова инструмента: наблюдение, запись и provenance."""

    tool: ToolName
    observation: dict[str, object]
    tool_call: ToolCall
    citations: tuple[Citation, ...] = ()
    product_refs: tuple[str, ...] = ()
    web_refs: tuple[str, ...] = ()
    price_refs: tuple[str, ...] = ()
    degradations: tuple[Degradation, ...] = ()


class ToolExecutor:
    """Исполнитель инструментов из закрытого allowlist."""

    def __init__(
        self,
        *,
        rag: ProductCatalogRagService,
        price: PriceAnalysisService,
        web: WebSearchService,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._rag = rag
        self._price = price
        self._web = web
        self._clock = clock
        self._ids = id_generator

    async def execute(
        self,
        tool: ToolName,
        raw_args: Mapping[str, object],
        *,
        step_index: int,
        run_id: AgentRunId,
    ) -> ExecutedTool:
        """Исполняет вызов; отказы превращает в наблюдение, не в исключение."""
        started = self._clock.now()
        try:
            return await self._dispatch(
                tool, raw_args, step_index, run_id, started
            )
        except (ValidationError, InvalidQuery) as exc:
            return self._failed(
                tool, raw_args, step_index, run_id, started, exc, rejected=True
            )
        except Exception as exc:  # отказ зависимости → деградация
            return self._failed(
                tool, raw_args, step_index, run_id, started, exc, rejected=False
            )

    async def _dispatch(
        self,
        tool: ToolName,
        raw_args: Mapping[str, object],
        step_index: int,
        run_id: AgentRunId,
        started: datetime,
    ) -> ExecutedTool:
        if tool is ToolName.PRODUCT_CATALOG_RAG:
            return await self._run_rag(raw_args, step_index, run_id, started)
        if tool is ToolName.PRICE_ANALYSIS:
            return await self._run_price(raw_args, step_index, run_id, started)
        return await self._run_web(raw_args, step_index, run_id, started)

    async def _run_rag(
        self,
        raw_args: Mapping[str, object],
        step_index: int,
        run_id: AgentRunId,
        started: datetime,
    ) -> ExecutedTool:
        args = ProductCatalogRagArgs.model_validate(dict(raw_args))
        context = await self._rag.retrieve(
            args.query, filters=args.to_filters()
        )
        refs = tuple(citation.ref for citation in context.citations)
        summary = {
            "products": len(context.products),
            "degraded": [d.dependency for d in context.degradations],
        }
        return ExecutedTool(
            tool=ToolName.PRODUCT_CATALOG_RAG,
            observation=rag_observation(context),
            tool_call=self._ok_call(
                ToolName.PRODUCT_CATALOG_RAG,
                raw_args,
                step_index,
                run_id,
                started,
                summary,
                context.citations,
            ),
            citations=context.citations,
            product_refs=refs,
            degradations=context.degradations,
        )

    async def _run_price(
        self,
        raw_args: Mapping[str, object],
        step_index: int,
        run_id: AgentRunId,
        started: datetime,
    ) -> ExecutedTool:
        args = PriceAnalysisArgs.model_validate(dict(raw_args))
        result = await self._price.analyze(
            args.to_selector(), bands=args.to_bands()
        )
        citation = Citation(
            source_type=CitationType.PRICE_ANALYSIS,
            ref=result.analysis_ref,
            title=f"Ценовой анализ: {result.count} товаров",
            snippet=f"медиана {result.price.median} {result.currency.code}",
            position=0,
            retrieved_at=started,
        )
        summary = {"count": result.count, "analysis_ref": result.analysis_ref}
        return ExecutedTool(
            tool=ToolName.PRICE_ANALYSIS,
            observation=price_observation(result),
            tool_call=self._ok_call(
                ToolName.PRICE_ANALYSIS,
                raw_args,
                step_index,
                run_id,
                started,
                summary,
                (citation,),
            ),
            citations=(citation,),
            price_refs=(result.analysis_ref,),
        )

    async def _run_web(
        self,
        raw_args: Mapping[str, object],
        step_index: int,
        run_id: AgentRunId,
        started: datetime,
    ) -> ExecutedTool:
        args = WebSearchArgs.model_validate(dict(raw_args))
        results = await self._web.search(args.query, k=args.k)
        citations = tuple(
            Citation(
                source_type=CitationType.WEB,
                ref=result.url,
                title=result.title,
                snippet=result.snippet,
                position=index,
                retrieved_at=started,
            )
            for index, result in enumerate(results)
        )
        summary = {"results": len(results)}
        return ExecutedTool(
            tool=ToolName.WEB_SEARCH,
            observation=web_observation(results),
            tool_call=self._ok_call(
                ToolName.WEB_SEARCH,
                raw_args,
                step_index,
                run_id,
                started,
                summary,
                citations,
            ),
            citations=citations,
            web_refs=tuple(result.url for result in results),
        )

    def _ok_call(
        self,
        tool: ToolName,
        raw_args: Mapping[str, object],
        step_index: int,
        run_id: AgentRunId,
        started: datetime,
        summary: dict[str, object],
        provenance: tuple[Citation, ...],
    ) -> ToolCall:
        finished = self._clock.now()
        return ToolCall(
            id=ToolCallId(self._ids.new_uuid7()),
            agent_run_id=run_id,
            step_index=step_index,
            tool=tool,
            status=ToolCallStatus.OK,
            started_at=started,
            finished_at=finished,
            latency_ms=_latency_ms(started, finished),
            arguments=dict(raw_args),
            result_summary=summary,
            provenance=provenance,
        )

    def _failed(
        self,
        tool: ToolName,
        raw_args: Mapping[str, object],
        step_index: int,
        run_id: AgentRunId,
        started: datetime,
        exc: Exception,
        *,
        rejected: bool,
    ) -> ExecutedTool:
        finished = self._clock.now()
        kind = "invalid_arguments" if rejected else "tool_failed"
        status = ToolCallStatus.REJECTED if rejected else ToolCallStatus.ERROR
        tool_call = ToolCall(
            id=ToolCallId(self._ids.new_uuid7()),
            agent_run_id=run_id,
            step_index=step_index,
            tool=tool,
            status=status,
            started_at=started,
            finished_at=finished,
            latency_ms=_latency_ms(started, finished),
            arguments=dict(raw_args),
            result_summary={"error": kind},
            error=str(exc)[:_DETAIL_MAX],
        )
        degradations = () if rejected else (Degradation(tool.value, "error"),)
        return ExecutedTool(
            tool=tool,
            observation={"error": kind, "detail": str(exc)[:_DETAIL_MAX]},
            tool_call=tool_call,
            degradations=degradations,
        )


def _latency_ms(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() * 1000)
