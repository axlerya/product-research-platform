"""Тесты метрик."""

from datetime import UTC, datetime
from uuid import UUID

from prometheus_client import CollectorRegistry

from research_agent_service.application.dto.answer import AnswerQueryResult
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import (
    Confidence,
    RunStatus,
    ToolName,
)
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
)
from research_agent_service.domain.value_objects.usage import TokenUsage
from research_agent_service.infrastructure.observability.metrics import (
    MetricsRecorder,
    build_metrics,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_build_metrics_registers_series() -> None:
    """Счётчик инкрементируется и виден в реестре."""
    registry = CollectorRegistry()
    metrics = build_metrics(registry)

    metrics.tool_calls_total.labels(tool="web_search", status="ok").inc()

    value = registry.get_sample_value(
        "research_agent_tool_calls_total",
        {"tool": "web_search", "status": "ok"},
    )
    assert value == 1.0


def test_separate_registries_do_not_collide() -> None:
    """Два независимых реестра не дают ошибки дублирования."""
    build_metrics(CollectorRegistry())
    build_metrics(CollectorRegistry())


def _result(*, degraded: bool = False) -> AnswerQueryResult:
    return AnswerQueryResult(
        agent_run_id=AgentRunId(UUID(int=1)),
        conversation_id=ConversationId(UUID(int=2)),
        status=RunStatus.DEGRADED if degraded else RunStatus.COMPLETED,
        answer="ответ",
        citations=(),
        used_tools=(ToolName.PRODUCT_CATALOG_RAG,),
        confidence=Confidence.HIGH,
        degradations=(
            (Degradation("reranker", "unavailable"),) if degraded else ()
        ),
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
        latency_ms=1200,
    )


def test_recorder_observes_query_series() -> None:
    """observe_query пишет латентность, токены, инструменты и деградации."""
    recorder = MetricsRecorder.create(model="qwen3")

    recorder.run_started()
    recorder.observe_query(_result(degraded=True), latency_s=1.2)
    recorder.run_finished()

    dump = recorder.render().decode("utf-8")
    assert "research_agent_query_seconds" in dump
    assert 'tool="product_catalog_rag"' in dump
    assert 'dependency="reranker"' in dump
    assert 'kind="prompt"' in dump


def test_recorder_counts_rate_limited() -> None:
    """rate_limited увеличивает счётчик отклонений."""
    recorder = MetricsRecorder.create()

    recorder.rate_limited()

    assert "research_agent_rate_limited_total 1.0" in recorder.render().decode(
        "utf-8"
    )
