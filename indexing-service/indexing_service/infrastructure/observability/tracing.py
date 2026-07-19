"""Distributed tracing (OpenTelemetry) — опционально через OTLP (§10).

FastStream OTel-middleware извлекает traceparent из заголовков RabbitMQ,
продолжая трейс, начатый catalog-service, и открывает спаны обработки.
"""

from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def build_tracer_provider(
    *, service_name: str, endpoint: str
) -> TracerProvider:
    """Строит ``TracerProvider`` с OTLP/HTTP-экспортом трейсов."""
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name})
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
    )
    return provider
