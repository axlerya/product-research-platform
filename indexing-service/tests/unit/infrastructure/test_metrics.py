"""Тесты прикладных метрик свежести (§9.6)."""

from prometheus_client import CollectorRegistry, generate_latest

from indexing_service.application.ports.metrics import NullMetrics
from indexing_service.infrastructure.observability.metrics import (
    BacklogGauges,
    build_metrics,
)


def _samples(registry: CollectorRegistry) -> dict[str, float]:
    return {
        line.split(" ")[0]: float(line.split(" ")[1])
        for line in generate_latest(registry).decode().splitlines()
        if line and not line.startswith("#")
    }


def test_applied_and_stale_are_counted_apart():
    registry = CollectorRegistry()
    metrics = build_metrics(registry)

    metrics.chunk_applied(applied=True)
    metrics.chunk_applied(applied=True)
    metrics.chunk_applied(applied=False)

    samples = _samples(registry)
    assert samples['embeddings_applied_total{outcome="applied"}'] == 2.0
    assert samples['embeddings_applied_total{outcome="stale"}'] == 1.0


def test_job_latency_is_split_by_outcome():
    registry = CollectorRegistry()
    metrics = build_metrics(registry)

    metrics.job_finished(latency_s=12.0, failed=False)
    metrics.job_finished(latency_s=30.0, failed=True)

    samples = _samples(registry)
    assert (
        samples['indexing_job_latency_seconds_sum{outcome="done"}'] == 12.0
    )
    assert (
        samples['indexing_job_latency_seconds_sum{outcome="failed"}'] == 30.0
    )


def test_backlog_gauges_are_registered():
    """Gauge'и отставания заведены — их снимает relay в своём цикле."""
    registry = CollectorRegistry()
    BacklogGauges(None, registry)

    exposed = _samples(registry)
    assert exposed["indexing_jobs_awaiting"] == 0.0
    assert exposed["outbox_lag_seconds"] == 0.0
    assert exposed["outbox_quarantined"] == 0.0


def test_null_metrics_swallow_everything():
    """Метрики не обязательны: use case работает и без них."""
    metrics = NullMetrics()
    assert metrics.chunk_applied(applied=True) is None
    assert metrics.job_finished(latency_s=1.0, failed=False) is None
