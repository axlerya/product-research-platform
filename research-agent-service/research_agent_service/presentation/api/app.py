"""Сборка FastAPI-приложения (composition — вне покрытия юнит-тестами)."""

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


def create_app(services: ApiServices) -> FastAPI:
    """Строит приложение с внедрёнными сервисами и маршрутами."""
    app = FastAPI(title="research-agent-service")
    app.state.services = services
    register_error_handlers(app)
    app.include_router(query.router)
    app.include_router(queries.router)
    app.include_router(health.router)
    return app
