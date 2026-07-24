"""Тесты построения провайдера трейсинга."""

from opentelemetry.sdk.trace import TracerProvider

from research_agent_service.infrastructure.observability.tracing import (
    build_tracer_provider,
)


def test_empty_endpoint_disables_tracing() -> None:
    """Пустой endpoint → None (глобальный провайдер остаётся no-op)."""
    assert build_tracer_provider(service_name="svc", otlp_endpoint="") is None


def test_endpoint_builds_provider_with_service_name() -> None:
    """Непустой endpoint → провайдер с ресурсом service.name."""
    provider = build_tracer_provider(
        service_name="research-agent-service",
        otlp_endpoint="http://collector:4317",
    )

    assert isinstance(provider, TracerProvider)
    assert (
        provider.resource.attributes["service.name"] == "research-agent-service"
    )
