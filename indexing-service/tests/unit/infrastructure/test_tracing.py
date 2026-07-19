"""Тесты сборки ``TracerProvider`` (OpenTelemetry)."""

from opentelemetry.sdk.trace import TracerProvider

from indexing_service.infrastructure.observability.tracing import (
    build_tracer_provider,
)


def test_build_tracer_provider_sets_service_name():
    provider = build_tracer_provider(
        service_name="indexing-service",
        endpoint="http://otel-collector:4318/v1/traces",
    )
    assert isinstance(provider, TracerProvider)
    assert provider.resource.attributes["service.name"] == "indexing-service"
