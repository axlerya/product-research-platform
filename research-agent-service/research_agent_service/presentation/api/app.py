"""Сборка FastAPI-приложения (composition — вне покрытия юнит-тестами)."""

from typing import Any

from fastapi import FastAPI

from research_agent_service.presentation.api.errors import (
    register_error_handlers,
)
from research_agent_service.presentation.api.routes import (
    health,
    queries,
    query,
)
from research_agent_service.presentation.api.services import ApiServices


def create_app(
    services: ApiServices | None = None,
    *,
    lifespan: Any = None,
) -> FastAPI:
    """Строит приложение с маршрутами.

    services заданы сразу (тесты) либо устанавливаются в app.state в lifespan
    (рантайм — сборка зависимостей на старте процесса).
    """
    app = FastAPI(title="research-agent-service", lifespan=lifespan)
    if services is not None:
        app.state.services = services
    register_error_handlers(app)
    app.include_router(query.router)
    app.include_router(queries.router)
    app.include_router(health.router)
    return app
