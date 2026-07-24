"""Тесты метрик."""

from prometheus_client import CollectorRegistry

from research_agent_service.infrastructure.observability.metrics import (
    build_metrics,
)


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
