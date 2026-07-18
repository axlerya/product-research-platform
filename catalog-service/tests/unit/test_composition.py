"""Smoke-тесты composition root (проводка bootstrap/main)."""

from fastapi import FastAPI

from catalog_service.application.use_cases.create_product import CreateProduct
from catalog_service.bootstrap import build_container
from catalog_service.infrastructure.config import Settings
from catalog_service.main import build_app
from catalog_service.presentation.api import deps


def test_container_builds_use_cases_and_services():
    container = build_container(Settings())
    assert isinstance(container.create_product_uc(), CreateProduct)
    assert container.product_query_service() is not None
    assert container.reference_query_service() is not None
    assert container.outbox_publisher() is not None


def test_build_app_wires_all_providers():
    app = build_app(build_container(Settings()))
    assert isinstance(app, FastAPI)
    for provider in (
        deps.get_create_product_uc,
        deps.get_update_content_uc,
        deps.get_update_commercial_uc,
        deps.get_set_stock_uc,
        deps.get_update_metrics_uc,
        deps.get_delete_product_uc,
        deps.get_product_query_service,
        deps.get_reference_query_service,
    ):
        assert provider in app.dependency_overrides
