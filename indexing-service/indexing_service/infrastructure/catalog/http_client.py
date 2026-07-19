"""HTTP-клиент к catalog-service (repair / reindex / reconcile).

Маппит ``ProductRead`` (деньги/рейтинг строкой) в ``ProductSnapshot``.
Сетевые/5xx сбои переводит в ``CatalogUnavailableError`` (временная).
"""

from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from uuid import UUID

import httpx

from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.exceptions import CatalogUnavailableError
from indexing_service.domain.value_objects.identifiers import ProductId


def _to_snapshot(data: dict) -> ProductSnapshot:
    """``ProductRead`` JSON → ``ProductSnapshot`` (строки → Decimal)."""
    source = data.get("source_updated_at")
    return ProductSnapshot(
        product_id=UUID(data["id"]),
        sku=data["sku"],
        name=data["name"],
        description=data["description"],
        category=data["category"],
        brand=data["brand"],
        supplier=data["supplier"],
        price=Decimal(data["price"]["amount"]),
        cost=Decimal(data["cost"]["amount"]),
        currency=data["price"]["currency"],
        stock=int(data["stock"]),
        sales_per_month=int(data["sales_per_month"]),
        avg_rating=Decimal(data["avg_rating"]),
        review_count=int(data["review_count"]),
        source_updated_at=date.fromisoformat(source) if source else None,
        aggregate_version=int(data["version"]),
    )


class HttpCatalogClient:
    """Читает товары из catalog-service по REST."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str) -> None:
        self._client = client
        self._base = base_url.rstrip("/")

    async def get_product(
        self, product_id: ProductId
    ) -> ProductSnapshot | None:
        url = f"{self._base}/api/v1/products/{product_id.value}"
        try:
            response = await self._client.get(url)
        except httpx.HTTPError as exc:
            raise CatalogUnavailableError(str(exc)) from exc
        if response.status_code == 404:
            return None
        if response.is_server_error:
            raise CatalogUnavailableError(
                f"catalog вернул {response.status_code}"
            )
        response.raise_for_status()
        return _to_snapshot(response.json())

    async def iter_products(
        self, *, batch: int = 100
    ) -> AsyncIterator[ProductSnapshot]:
        offset = 0
        while True:
            page = await self._fetch_page(limit=batch, offset=offset)
            items = page["items"]
            for item in items:
                yield _to_snapshot(item)
            offset += len(items)
            if not items or offset >= page["total"]:
                break

    async def _fetch_page(self, *, limit: int, offset: int) -> dict:
        url = f"{self._base}/api/v1/products"
        params = {"limit": limit, "offset": offset, "sort": "sku"}
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CatalogUnavailableError(str(exc)) from exc
        return response.json()
