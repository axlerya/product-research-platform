"""OpenTelemetry tracer provider (opt-in по OTLP-endpoint, §10.1)."""

from typing import Any


def build_tracer_provider(*, service_name: str, endpoint: str) -> Any | None:
    """Строит ``TracerProvider`` с OTLP-экспортом.

    Возвращает ``None``, если endpoint не задан (трейсинг — no-op, нулевая
    цена). Тяжёлые импорты OTel — лениво, только когда endpoint есть.

    Args:
        service_name: Имя сервиса (атрибут ресурса).
        endpoint: OTLP/HTTP endpoint; пусто → выключено.

    Returns:
        ``TracerProvider`` или ``None``.
    """
    if not endpoint:
        return None
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name})
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
    )
    return provider
