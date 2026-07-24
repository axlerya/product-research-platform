"""Тесты HTTP-маршрутов через TestClient на фейковых use cases."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from research_agent_service.application.dto.answer import AnswerQueryResult
from research_agent_service.application.exceptions import (
    QueryFailed,
    RateLimited,
    UnknownAgentRun,
)
from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.value_objects.enums import (
    Confidence,
    RunStatus,
)
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    MessageId,
)
from research_agent_service.domain.value_objects.usage import TokenUsage
from research_agent_service.infrastructure.observability.metrics import (
    MetricsRecorder,
)
from research_agent_service.presentation.api.app import create_app
from research_agent_service.presentation.api.services import ApiServices

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_RUN_ID = UUID(int=1)
_CONV_ID = UUID(int=2)


class _FakeAnswerQuery:
    def __init__(self, *, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.command = None

    async def execute(self, command):
        self.command = command
        if self.error is not None:
            raise self.error
        return self.result


class _FakeSubmitFeedback:
    def __init__(self, *, error=None) -> None:
        self.error = error
        self.command = None

    async def execute(self, command):
        self.command = command
        if self.error is not None:
            raise self.error


class _FakeListQueries:
    def __init__(self, runs=()) -> None:
        self.runs = runs
        self.kwargs = None

    async def execute(self, **kwargs):
        self.kwargs = kwargs
        return self.runs


class _FakeGetQuery:
    def __init__(self, run=None) -> None:
        self.run = run

    async def execute(self, run_id):
        return self.run


def _result() -> AnswerQueryResult:
    return AnswerQueryResult(
        agent_run_id=AgentRunId(_RUN_ID),
        conversation_id=ConversationId(_CONV_ID),
        status=RunStatus.COMPLETED,
        answer="вот ответ",
        citations=(),
        used_tools=(),
        confidence=Confidence.HIGH,
        degradations=(),
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
        latency_ms=42,
    )


def _run() -> AgentRun:
    run = AgentRun(
        id=AgentRunId(_RUN_ID),
        conversation_id=ConversationId(_CONV_ID),
        query_message_id=MessageId(UUID(int=3)),
        model="qwen3",
        prompt_version="v1",
        started_at=_NOW,
    )
    run.complete(
        answer_message_id=MessageId(UUID(int=4)),
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
        confidence=Confidence.HIGH,
        degradations=(),
        loop_steps=1,
        now=_NOW,
    )
    return run


def _client(
    *,
    answer_query=None,
    submit_feedback=None,
    list_queries=None,
    get_query=None,
    ready=True,
    metrics=None,
) -> TestClient:
    async def _readiness() -> bool:
        return ready

    services = ApiServices(
        answer_query=answer_query or _FakeAnswerQuery(result=_result()),
        submit_feedback=submit_feedback or _FakeSubmitFeedback(),
        list_queries=list_queries or _FakeListQueries(),
        get_query=get_query or _FakeGetQuery(),
        readiness=_readiness,
        metrics=metrics,
    )
    return TestClient(create_app(services))


def test_post_query_ok() -> None:
    """Успех: 200 с телом ответа и проброс client_principal."""
    answer = _FakeAnswerQuery(result=_result())
    client = _client(answer_query=answer)

    response = client.post(
        "/query",
        json={"text": "найди наушники"},
        headers={"X-Client-Principal": "client-9"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "вот ответ"
    assert body["status"] == "completed"
    assert answer.command.client_principal == "client-9"


def test_post_query_rate_limited() -> None:
    """RateLimited → 429 с Retry-After."""
    answer = _FakeAnswerQuery(error=RateLimited(retry_after_s=30.0))
    response = _client(answer_query=answer).post(
        "/query", json={"text": "вопрос"}
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json()["error"] == "rate_limited"


def test_post_query_rate_limited_without_retry_after() -> None:
    """RateLimited без retry_after → 429 без заголовка Retry-After."""
    answer = _FakeAnswerQuery(error=RateLimited())
    response = _client(answer_query=answer).post(
        "/query", json={"text": "вопрос"}
    )

    assert response.status_code == 429
    assert "Retry-After" not in response.headers


def test_post_query_failed() -> None:
    """QueryFailed → 502."""
    answer = _FakeAnswerQuery(error=QueryFailed(AgentRunId(_RUN_ID)))
    response = _client(answer_query=answer).post(
        "/query", json={"text": "вопрос"}
    )

    assert response.status_code == 502
    assert response.json()["error"] == "query_failed"


def test_post_query_schema_validation() -> None:
    """Пустой text не проходит схему → 422."""
    response = _client().post("/query", json={"text": ""})
    assert response.status_code == 422


def test_post_query_domain_validation() -> None:
    """Пробельный text отвергается доменом → 422 invalid_request."""
    response = _client().post("/query", json={"text": "   "})
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"


def test_get_queries_lists_with_filters() -> None:
    """GET /queries отдаёт список и прокидывает фильтры в use case."""
    listing = _FakeListQueries(runs=(_run(),))
    response = _client(list_queries=listing).get(
        "/queries", params={"status": "completed", "limit": 5}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["limit"] == 5
    assert listing.kwargs["status"] is RunStatus.COMPLETED


def test_get_query_found() -> None:
    """GET /queries/{id} найден → 200 с деталями."""
    response = _client(get_query=_FakeGetQuery(run=_run())).get(
        f"/queries/{_RUN_ID}"
    )
    assert response.status_code == 200
    assert response.json()["agent_run_id"] == str(_RUN_ID)


def test_get_query_not_found() -> None:
    """GET /queries/{id} не найден → 404."""
    response = _client(get_query=_FakeGetQuery(run=None)).get(
        f"/queries/{_RUN_ID}"
    )
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_post_feedback_ok() -> None:
    """Обратная связь принята → 204, команда доходит до use case."""
    feedback = _FakeSubmitFeedback()
    response = _client(submit_feedback=feedback).post(
        f"/queries/{_RUN_ID}/feedback", json={"rating": "up"}
    )

    assert response.status_code == 204
    assert feedback.command.agent_run_id.value == _RUN_ID


def test_post_feedback_unknown_run() -> None:
    """Обратная связь по несуществующему прогону → 404."""
    feedback = _FakeSubmitFeedback(error=UnknownAgentRun("нет"))
    response = _client(submit_feedback=feedback).post(
        f"/queries/{_RUN_ID}/feedback", json={"rating": "down"}
    )

    assert response.status_code == 404


def test_health_ok() -> None:
    """GET /health → 200."""
    response = _client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(("ready", "code"), [(True, 200), (False, 503)])
def test_ready_reflects_probe(ready: bool, code: int) -> None:
    """GET /ready отражает пробу готовности."""
    response = _client(ready=ready).get("/ready")
    assert response.status_code == code


def test_query_records_metrics_and_metrics_endpoint() -> None:
    """Успешный запрос пишет метрики, /metrics их отдаёт."""
    recorder = MetricsRecorder.create(model="qwen3")
    client = _client(metrics=recorder)

    assert client.post("/query", json={"text": "вопрос"}).status_code == 200

    dump = client.get("/metrics")
    assert dump.status_code == 200
    assert "research_agent_query_seconds" in dump.text
    assert "research_agent_active_runs" in dump.text


def test_rate_limited_records_metric() -> None:
    """Отклонение по лимиту увеличивает счётчик и остаётся 429."""
    recorder = MetricsRecorder.create()
    answer = _FakeAnswerQuery(error=RateLimited(retry_after_s=1.0))
    client = _client(answer_query=answer, metrics=recorder)

    assert client.post("/query", json={"text": "q"}).status_code == 429
    assert (
        "research_agent_rate_limited_total 1.0" in client.get("/metrics").text
    )


def test_metrics_endpoint_absent_without_recorder() -> None:
    """Без подключённой записи метрик /metrics отвечает 404."""
    assert _client().get("/metrics").status_code == 404
