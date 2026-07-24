"""ASGI-точка входа: собирает FastAPI и проводит зависимости.

Запуск: ``uvicorn catalog_service.main:app``.
"""

from fastapi import FastAPI

from catalog_service.bootstrap import Container, build_container
from catalog_service.presentation.api import deps
from catalog_service.presentation.api.app import create_app


def build_app(container: Container | None = None) -> FastAPI:
    """Создаёт приложение и связывает провайдеры use cases/запросов."""
    container = container or build_container()
    app = create_app()
    overrides = {
        deps.get_create_product_uc: container.create_product_uc,
        deps.get_update_content_uc: container.update_content_uc,
        deps.get_update_commercial_uc: container.update_commercial_uc,
        deps.get_set_stock_uc: container.set_stock_uc,
        deps.get_update_metrics_uc: container.update_metrics_uc,
        deps.get_delete_product_uc: container.delete_product_uc,
        deps.get_product_query_service: container.product_query_service,
        deps.get_reference_query_service: container.reference_query_service,
        deps.get_analyze_prices: container.analyze_prices,
    }
    app.dependency_overrides.update(overrides)
    return app


app = build_app()
