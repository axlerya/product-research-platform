"""Тесты ``HttpCatalogClient`` через ``httpx.MockTransport`` (без сети)."""

from decimal import Decimal
from uuid import UUID

import httpx
import pytest

from indexing_service.application.exceptions import CatalogUnavailableError
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.infrastructure.catalog.http_client import (
    HttpCatalogClient,
)


def _product_json(product_id: UUID, version: int = 1) -> dict:
    return {
        "id": str(product_id),
        "sku": "PROD-001",
        "name": "Наушники",
        "description": "Беспроводные",
        "category": "Электроника",
        "brand": "AudioMax",
        "supplier": "TechSupply",
        "price": {"amount": "129.99", "currency": "RUB"},
        "cost": {"amount": "65.00", "currency": "RUB"},
        "stock": 245,
        "is_in_stock": True,
        "sales_per_month": 87,
        "avg_rating": "4.50",
        "review_count": 1243,
        "margin": {
            "profit": {"amount": "64.99", "currency": "RUB"},
            "percent": "50.00",
        },
        "source_updated_at": "2024-03-15",
        "version": version,
        "is_deleted": False,
        "created_at": "2026-07-19T00:00:00Z",
        "updated_at": "2026-07-19T00:00:00Z",
    }


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_get_product_maps_snapshot():
    pid = ProductId(UUID(int=1))

    def handler(request):
        assert request.url.path == f"/api/v1/products/{pid.value}"
        return httpx.Response(200, json=_product_json(pid.value, version=3))

    async with _client(handler) as http:
        snapshot = await HttpCatalogClient(
            http, base_url="http://catalog"
        ).get_product(pid)

    assert snapshot.price == Decimal("129.99")
    assert snapshot.currency == "RUB"
    assert snapshot.avg_rating == Decimal("4.50")
    assert snapshot.sales_per_month == 87
    assert snapshot.aggregate_version == 3


async def test_get_product_404_returns_none():
    def handler(request):
        return httpx.Response(404, json={"title": "nf", "status": 404})

    async with _client(handler) as http:
        result = await HttpCatalogClient(
            http, base_url="http://catalog"
        ).get_product(ProductId(UUID(int=2)))
    assert result is None


async def test_get_product_5xx_raises_unavailable():
    def handler(request):
        return httpx.Response(503)

    async with _client(handler) as http:
        with pytest.raises(CatalogUnavailableError):
            await HttpCatalogClient(
                http, base_url="http://catalog"
            ).get_product(ProductId(UUID(int=3)))


async def test_iter_products_paginates_offset():
    pid1, pid2 = UUID(int=10), UUID(int=11)

    def handler(request):
        offset = int(request.url.params["offset"])
        item = _product_json(pid1) if offset == 0 else _product_json(pid2)
        return httpx.Response(
            200,
            json={"items": [item], "total": 2, "limit": 1, "offset": offset},
        )

    async with _client(handler) as http:
        client = HttpCatalogClient(http, base_url="http://catalog")
        snapshots = [s async for s in client.iter_products(batch=1)]

    assert len(snapshots) == 2
    assert {str(s.product_id) for s in snapshots} == {str(pid1), str(pid2)}
