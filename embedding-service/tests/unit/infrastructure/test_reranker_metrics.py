"""Unit-тесты метрик reranker — отдельный набор (имена ``reranker_*``)."""

from prometheus_client import CollectorRegistry, generate_latest

from embedding_service.infrastructure.observability.reranker_metrics import (
    RerankerMetrics,
    build_reranker_metrics,
)


def test_builds_metrics_and_exercises_them() -> None:
    registry = CollectorRegistry()
    metrics = build_reranker_metrics(registry)
    assert isinstance(metrics, RerankerMetrics)
    metrics.inference_seconds.observe(0.1)
    metrics.documents.observe(5)
    metrics.batch_size.observe(3)
    metrics.score.observe(0.7)
    metrics.requests_total.labels(status="ok").inc()
    metrics.errors_total.labels(type="InferenceError").inc()
    metrics.timeouts_total.inc()
    metrics.oom_total.inc()
    metrics.inflight.set(2)
    metrics.model_info.labels(
        model_version="m@r|norm=1", device="cpu", precision="fp32"
    ).set(1)


def test_metrics_exposed_with_reranker_prefix() -> None:
    registry = CollectorRegistry()
    metrics = build_reranker_metrics(registry)
    metrics.requests_total.labels(status="ok").inc()
    metrics.inflight.set(1)
    output = generate_latest(registry).decode()
    assert "reranker_requests_total" in output
    assert "reranker_inflight" in output


def test_metrics_isolated_from_embedding_registry() -> None:
    # Пустой реестр — набор reranker самодостаточен, без глобального состояния.
    registry = CollectorRegistry()
    build_reranker_metrics(registry)
    families = {family.name for family in registry.collect()}
    assert all(
        name.startswith("reranker_") or name == "reranker" for name in families
    )
