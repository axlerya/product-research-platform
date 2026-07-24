"""Тесты ToolExecutor на фейковых прикладных сервисах."""

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from research_agent_service.application.dto.price_analysis import (
    MarginStats,
    PriceAnalysisResult,
    PriceStats,
)
from research_agent_service.application.dto.retrieval import (
    RagContext,
    RankedProduct,
)
from research_agent_service.application.dto.web import WebResult
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.currency import Currency
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import (
    CitationType,
    ToolCallStatus,
    ToolName,
)
from research_agent_service.domain.value_objects.identifiers import AgentRunId
from research_agent_service.infrastructure.agent.executor import ToolExecutor

_RUN = AgentRunId(UUID(int=1))
_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_RUB = Currency("RUB")


class _FakeClock:
    def now(self) -> datetime:
        return _NOW


class _FakeIds:
    def __init__(self) -> None:
        self._n = 0

    def new_uuid7(self) -> UUID:
        self._n += 1
        return UUID(int=self._n)


class _FakeRag:
    def __init__(
        self,
        *,
        context: RagContext | None = None,
        error: Exception | None = None,
    ) -> None:
        self._context = context
        self._error = error
        self.query: str | None = None

    async def retrieve(
        self, query: str, *, filters: object = None
    ) -> RagContext:
        if self._error is not None:
            raise self._error
        self.query = query
        assert self._context is not None
        return self._context


class _FakePrice:
    def __init__(self, *, result: PriceAnalysisResult) -> None:
        self._result = result

    async def analyze(
        self, selector: object, *, bands: object = ()
    ) -> PriceAnalysisResult:
        return self._result


class _FakeWeb:
    def __init__(self, *, results: tuple[WebResult, ...]) -> None:
        self._results = results

    async def search(self, query: str, *, k: int) -> tuple[WebResult, ...]:
        return self._results


def _executor(
    *,
    rag: _FakeRag | None = None,
    price: _FakePrice | None = None,
    web: _FakeWeb | None = None,
) -> ToolExecutor:
    return ToolExecutor(
        rag=rag or _FakeRag(context=RagContext(products=(), citations=())),
        price=price or _FakePrice(result=_price_result()),
        web=web or _FakeWeb(results=()),
        clock=_FakeClock(),
        id_generator=_FakeIds(),
    )


def _citation(ref: str) -> Citation:
    return Citation(
        source_type=CitationType.PRODUCT,
        ref=ref,
        title="Наушники",
        snippet="s",
        position=0,
        retrieved_at=_NOW,
        score=Decimal("0.9"),
    )


def _price_result() -> PriceAnalysisResult:
    return PriceAnalysisResult(
        count=2,
        currency=_RUB,
        price=PriceStats(
            min=Decimal("10"),
            max=Decimal("30"),
            avg=Decimal("20"),
            median=Decimal("20"),
            stddev=Decimal("5"),
        ),
        margin=MarginStats(
            min_percent=Decimal("5"),
            max_percent=Decimal("40"),
            avg_percent=Decimal("22"),
            median_percent=Decimal("20"),
            undefined_count=0,
            negative_count=0,
        ),
        analysis_ref="analysis-1",
    )


async def _run(executor: ToolExecutor, tool: ToolName, args: Mapping) -> object:
    return await executor.execute(tool, args, step_index=0, run_id=_RUN)


async def test_rag_success_collects_refs_and_degradations() -> None:
    """RAG: наблюдение, OK-вызов, product_refs из цитат, деградации."""
    context = RagContext(
        products=(
            RankedProduct(
                sku="SKU-1", name="Наушники", category="Аудио", snippet="s"
            ),
        ),
        citations=(_citation("SKU-1"),),
        degradations=(Degradation("reranker", "unavailable"),),
    )
    executed = await _run(
        _executor(rag=_FakeRag(context=context)),
        ToolName.PRODUCT_CATALOG_RAG,
        {"query": "наушники"},
    )

    assert executed.tool_call.status is ToolCallStatus.OK
    assert executed.product_refs == ("SKU-1",)
    assert executed.degradations == (Degradation("reranker", "unavailable"),)
    assert executed.observation["products"][0]["sku"] == "SKU-1"
    assert executed.tool_call.agent_run_id == _RUN


async def test_price_success_builds_citation_and_ref() -> None:
    """price_analysis: одна цитата с analysis_ref, price_refs."""
    executed = await _run(
        _executor(), ToolName.PRICE_ANALYSIS, {"skus": ["SKU-1", "SKU-2"]}
    )

    assert executed.price_refs == ("analysis-1",)
    assert len(executed.citations) == 1
    assert executed.citations[0].source_type is CitationType.PRICE_ANALYSIS
    assert executed.citations[0].ref == "analysis-1"
    assert executed.observation["analysis_ref"] == "analysis-1"


async def test_web_success_builds_web_citations() -> None:
    """web_search: цитаты и web_refs из URL результатов."""
    web = _FakeWeb(
        results=(
            WebResult(title="A", url="https://ex.com/a", snippet="s"),
            WebResult(title="B", url="https://ex.com/b", snippet="s"),
        )
    )
    executed = await _run(
        _executor(web=web), ToolName.WEB_SEARCH, {"query": "обзор", "k": 2}
    )

    assert executed.web_refs == ("https://ex.com/a", "https://ex.com/b")
    assert all(c.source_type is CitationType.WEB for c in executed.citations)
    assert len(executed.observation["results"]) == 2


async def test_invalid_arguments_are_rejected_without_degradation() -> None:
    """Отсутствует обязательный query → REJECTED, без деградации."""
    executed = await _run(_executor(), ToolName.PRODUCT_CATALOG_RAG, {})

    assert executed.tool_call.status is ToolCallStatus.REJECTED
    assert executed.degradations == ()
    assert executed.observation["error"] == "invalid_arguments"
    assert executed.citations == ()


async def test_dependency_failure_is_error_with_degradation() -> None:
    """Отказ зависимости → ERROR + деградация инструмента."""
    rag = _FakeRag(error=RuntimeError("embedding down"))
    executed = await _run(
        _executor(rag=rag), ToolName.PRODUCT_CATALOG_RAG, {"query": "x"}
    )

    assert executed.tool_call.status is ToolCallStatus.ERROR
    assert executed.degradations == (
        Degradation("product_catalog_rag", "error"),
    )
    assert executed.observation["error"] == "tool_failed"
    assert executed.tool_call.error is not None
