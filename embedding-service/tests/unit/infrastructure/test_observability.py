"""Unit-тесты наблюдаемости: метрики, structured logging, tracing."""

import json
import logging

from prometheus_client import CollectorRegistry

from embedding_service.infrastructure.observability.logging import (
    JsonFormatter,
    bind_context,
    clear_context,
    configure_logging,
)
from embedding_service.infrastructure.observability.metrics import (
    build_metrics,
)
from embedding_service.infrastructure.observability.tracing import (
    build_tracer_provider,
)


def _record() -> logging.LogRecord:
    return logging.LogRecord(
        "test", logging.INFO, "f.py", 1, "hello %s", ("x",), None
    )


def test_build_metrics_registers_and_usable() -> None:
    registry = CollectorRegistry()
    metrics = build_metrics(registry)
    metrics.requests_total.labels(
        transport="grpc", kind="query", status="ok"
    ).inc()
    metrics.inference_seconds.labels(kind="query").observe(0.01)
    metrics.inflight.set(1)
    metrics.model_info.labels(
        model_version="k", device="cpu", precision="fp32"
    ).set(1)
    value = registry.get_sample_value(
        "embedding_requests_total",
        {"transport": "grpc", "kind": "query", "status": "ok"},
    )
    assert value == 1.0


def test_logging_context_injected() -> None:
    clear_context()
    bind_context(request_id="r1", model_version="k", empty=None)
    payload = json.loads(JsonFormatter().format(_record()))
    assert payload["message"] == "hello x"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "r1"
    assert payload["model_version"] == "k"
    assert "empty" not in payload
    clear_context()


def test_clear_context_removes_fields() -> None:
    bind_context(a="1")
    clear_context()
    payload = json.loads(JsonFormatter().format(_record()))
    assert "a" not in payload


def test_configure_logging_sets_json_handler() -> None:
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        configure_logging("DEBUG")
        assert root.level == logging.DEBUG
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


def test_tracing_disabled_without_endpoint() -> None:
    assert build_tracer_provider(service_name="x", endpoint="") is None


def test_tracing_provider_built_with_endpoint() -> None:
    provider = build_tracer_provider(
        service_name="embedding-service",
        endpoint="http://localhost:4318/v1/traces",
    )
    assert provider is not None
    provider.shutdown()
