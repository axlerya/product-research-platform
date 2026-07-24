"""Distributed tracing (OpenTelemetry, экспорт OTLP/gRPC).

Пустой otlp_endpoint = трейсинг выключен: возвращается None, глобальный
провайдер остаётся no-op. Построение провайдера не трогает глобальное
состояние — установку (`set_tracer_provider`) делает composition root.
"""

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def build_tracer_provider(
    *, service_name: str, otlp_endpoint: str
) -> TracerProvider | None:
    """Строит провайдер трейсинга или None, если endpoint пуст."""
    if not otlp_endpoint:
        return None
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
    )
    return provider
