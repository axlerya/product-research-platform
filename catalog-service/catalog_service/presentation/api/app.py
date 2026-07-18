"""Сборка FastAPI-приложения (без wiring зависимостей).

Провайдеры use cases/query-сервисов связывает composition root
(``bootstrap``) через ``dependency_overrides``; здесь только роутеры и
обработчики ошибок.
"""

from fastapi import FastAPI

from catalog_service.presentation.api.errors import register_error_handlers
from catalog_service.presentation.api.routers import (
    analytics,
    health,
    product_queries,
    products,
    references,
)


def create_app() -> FastAPI:
    """Создаёт приложение FastAPI с роутерами и обработчиками ошибок."""
    app = FastAPI(title="catalog-service", version="0.1.0")
    register_error_handlers(app)
    app.include_router(products.router)
    app.include_router(product_queries.router)
    app.include_router(references.router)
    app.include_router(analytics.router)
    app.include_router(health.router)
    return app
