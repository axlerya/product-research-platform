"""E2E путь запроса: реальный app + use cases + оркестратор + Postgres.

Заглушены только LLM и внешние источники данных инструментов. Проверяется
сквозной поток POST /query → agent loop → проверка источников → атомарная
запись прогона, вызовов и события в реальный Postgres, затем чтение и
обратная связь через API.
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from research_agent_service.application.dto.answer import RateVerdict
from research_agent_service.application.dto.retrieval import (
    RagContext,
    RankedProduct,
)
from research_agent_service.application.services.source_validation import (
    SourceValidator,
)
from research_agent_service.application.use_cases.answer_query import (
    AnswerQueryUseCase,
)
from research_agent_service.application.use_cases.read_queries import (
    GetQueryUseCase,
    ListQueriesUseCase,
)
from research_agent_service.application.use_cases.submit_feedback import (
    SubmitFeedbackUseCase,
)
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.enums import CitationType
from research_agent_service.infrastructure.agent.executor import ToolExecutor
from research_agent_service.infrastructure.agent.orchestrator import (
    LangGraphOrchestrator,
)
from research_agent_service.infrastructure.db.models import (
    AgentRunORM,
    FeedbackORM,
    OutboxEventORM,
    ToolCallORM,
)
from research_agent_service.infrastructure.db.unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from research_agent_service.infrastructure.services.clock import SystemClock
from research_agent_service.infrastructure.services.id_generator import (
    Uuid7Generator,
)
from research_agent_service.presentation.api.app import create_app
from research_agent_service.presentation.api.services import ApiServices
from tests.support.fakes import FakeCache

pytestmark = pytest.mark.e2e

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


class _StubModel:
    """Заглушка LLM: bind_tools возвращает себя, ainvoke отдаёт очередь."""

    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)

    def bind_tools(self, tools: object) -> "_StubModel":
        return self

    async def ainvoke(self, messages: object) -> AIMessage:
        return self._responses.pop(0)


class _FakeRag:
    async def retrieve(
        self, query: str, *, filters: object = None
    ) -> RagContext:
        return RagContext(
            products=(
                RankedProduct(
                    sku="SKU-1",
                    name="Наушники",
                    category="Аудио",
                    snippet="Беспроводные",
                ),
            ),
            citations=(
                Citation(
                    source_type=CitationType.PRODUCT,
                    ref="SKU-1",
                    title="Наушники",
                    snippet="Беспроводные",
                    position=0,
                    retrieved_at=_NOW,
                ),
            ),
            degradations=(),
        )


class _UnusedPrice:
    async def analyze(self, selector: object, *, bands: object = ()) -> object:
        raise AssertionError("price_analysis не должен вызываться")


class _UnusedWeb:
    async def search(self, query: str, *, k: int) -> object:
        raise AssertionError("web_search не должен вызываться")


class _AllowRateLimiter:
    async def check(
        self, key: str, *, limit: int, window_s: int
    ) -> RateVerdict:
        return RateVerdict(allowed=True)


async def _ready() -> bool:
    return True


def _model() -> _StubModel:
    return _StubModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "product_catalog_rag",
                        "args": {"query": "наушники"},
                        "id": "call-1",
                    }
                ],
                usage_metadata={
                    "input_tokens": 12,
                    "output_tokens": 4,
                    "total_tokens": 16,
                },
            ),
            AIMessage(
                content="Нашёл беспроводные наушники (SKU-1).",
                usage_metadata={
                    "input_tokens": 8,
                    "output_tokens": 6,
                    "total_tokens": 14,
                },
            ),
        ]
    )


def _app(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    cache: object = None,
) -> object:
    clock = SystemClock()
    ids = Uuid7Generator()
    executor = ToolExecutor(
        rag=_FakeRag(),
        price=_UnusedPrice(),
        web=_UnusedWeb(),
        clock=clock,
        id_generator=ids,
    )
    orchestrator = LangGraphOrchestrator(
        model=_model(), executor=executor, id_generator=ids
    )
    uow = SqlAlchemyUnitOfWork(session_factory=session_factory)
    services = ApiServices(
        answer_query=AnswerQueryUseCase(
            uow=uow,
            orchestrator=orchestrator,
            rate_limiter=_AllowRateLimiter(),
            source_validator=SourceValidator(),
            id_generator=ids,
            clock=clock,
            model="stub-llm",
            cache=cache,
        ),
        submit_feedback=SubmitFeedbackUseCase(
            uow=uow, id_generator=ids, clock=clock
        ),
        list_queries=ListQueriesUseCase(uow=uow),
        get_query=GetQueryUseCase(uow=uow),
        readiness=_ready,
    )
    return create_app(services)


def _client(app: object) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_query_path_persists_run_tool_call_and_event(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """POST /query проходит весь путь и пишет прогон, вызов и событие."""
    app = _app(session_factory)
    async with _client(app) as client:
        response = await client.post("/query", json={"text": "найди наушники"})

    assert response.status_code == 200
    body = response.json()
    assert "SKU-1" in body["answer"]
    assert body["used_tools"] == ["product_catalog_rag"]
    assert body["citations"][0]["ref"] == "SKU-1"
    run_id = UUID(body["agent_run_id"])

    async with session_factory() as session:
        run = await session.get(AgentRunORM, run_id)
        assert run is not None
        assert run.status == "completed"
        tool_calls = (
            await session.scalars(
                select(ToolCallORM).where(ToolCallORM.agent_run_id == run_id)
            )
        ).all()
        assert len(tool_calls) == 1
        assert tool_calls[0].agent_run_id == run_id
        assert tool_calls[0].tool == "product_catalog_rag"
        events = (await session.scalars(select(OutboxEventORM))).all()
        assert [e.event_type for e in events] == ["agent.query.completed.v1"]

    async with _client(app) as client:
        listing = await client.get("/queries")
        detail = await client.get(f"/queries/{run_id}")

    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1
    assert detail.status_code == 200
    assert detail.json()["agent_run_id"] == str(run_id)


async def test_feedback_path_persists_feedback_and_events(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Негативная обратная связь пишет отзыв и запрос оценки в outbox."""
    app = _app(session_factory)
    async with _client(app) as client:
        run_id = UUID(
            (await client.post("/query", json={"text": "q"})).json()[
                "agent_run_id"
            ]
        )
        feedback = await client.post(
            f"/queries/{run_id}/feedback",
            json={"rating": "down", "reason": "неточно"},
        )

    assert feedback.status_code == 204
    async with session_factory() as session:
        feedbacks = (await session.scalars(select(FeedbackORM))).all()
        assert len(feedbacks) == 1
        assert feedbacks[0].agent_run_id == run_id
        events = [
            e.event_type
            for e in (await session.scalars(select(OutboxEventORM))).all()
        ]
        assert "agent.feedback.received.v1" in events
        assert "agent.evaluation.requested.v1" in events


async def test_idempotent_query_replays_without_new_run(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Повтор с тем же idempotency_key не создаёт новый прогон."""
    app = _app(session_factory, cache=FakeCache())
    body = {"text": "найди наушники", "idempotency_key": "idem-e2e"}
    async with _client(app) as client:
        first = await client.post("/query", json=body)
        second = await client.post("/query", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["agent_run_id"] == second.json()["agent_run_id"]
    assert first.json()["answer"] == second.json()["answer"]

    async with session_factory() as session:
        runs = (await session.scalars(select(AgentRunORM))).all()
    assert len(runs) == 1
