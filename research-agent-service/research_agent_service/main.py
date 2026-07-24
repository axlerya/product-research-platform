"""ASGI-точка входа: приложение с lifespan-сборкой (вне покрытия).

uvicorn запускает research_agent_service.main:app. Зависимости собираются на
старте процесса (в работающем loop), логирование и трейсинг настраиваются там
же; на остановке ресурсы закрываются.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry import trace

from research_agent_service.bootstrap import build_container
from research_agent_service.infrastructure.config import get_settings
from research_agent_service.infrastructure.observability.logging import (
    configure_logging,
)
from research_agent_service.infrastructure.observability.tracing import (
    build_tracer_provider,
)
from research_agent_service.presentation.api.app import create_app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    provider = build_tracer_provider(
        service_name=settings.service_name,
        otlp_endpoint=settings.otlp_endpoint,
    )
    if provider is not None:
        trace.set_tracer_provider(provider)
    container = build_container(settings)
    app.state.services = container.api_services
    try:
        yield
    finally:
        await container.aclose()


def build_app() -> FastAPI:
    """Строит ASGI-приложение с lifespan."""
    return create_app(lifespan=_lifespan)


app = build_app()
