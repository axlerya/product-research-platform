"""Тесты HttpCatalogClient на httpx.MockTransport."""

from collections.abc import Callable
from decimal import Decimal

import httpx
import pytest

from research_agent_service.application.dto.price_analysis import (
    MarginBandSpec,
    ProductSelector,
)
from research_agent_service.application.exceptions import CatalogUnavailable
from research_agent_service.domain.value_objects.currency import Currency
from research_agent_service.domain.value_objects.money import Money
from research_agent_service.infrastructure.catalog.rest_client import (
    HttpCatalogClient,
)

_PRODUCT = {
    "sku": "SKU-1",
    "name": "Наушники",
    "category": "Аудио",
    "brand": "B",
    "supplier": "S",
    "price": {"amount": "129.99", "currency": "RUB"},
    "cost": {"amount": "80.00", "currency": "RUB"},
    "stock": 5,
    "is_in_stock": True,
    "margin": {
        "profit": {"amount": "49.99", "currency": "RUB"},
        "percent": "38.46",
    },
}

_ANALYSIS = {
    "count": 42,
    "currency": "RUB",
    "price": {
        "min": "100.00",
        "max": "5000.00",
        "avg": "1200.00",
        "median": "900.00",
        "stddev": "300.00",
    },
    "margin": {
        "min_percent": "5.00",
        "max_percent": "40.00",
        "avg_percent": "22.00",
        "median_percent": "20.00",
        "undefined_count": 1,
        "negative_count": 0,
    },
    "analysis_ref": "slice-1",
    "bands": [
        {
            "label": "0-10%",
            "lower_percent": "0",
            "upper_percent": "10",
            "count": 12,
        }
    ],
    "outliers": [
        {
            "sku": "SKU-9",
            "price": {"amount": "9999.00", "currency": "RUB"},
            "reason": "iqr",
            "score": "3.1",
        }
    ],
}


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> HttpCatalogClient:
    transport = httpx.MockTransport(handler)
    return HttpCatalogClient(
        client=httpx.AsyncClient(transport=transport, base_url="http://catalog")
    )


async def test_get_products_by_skus_parses_money() -> None:
    """Batch-чтение разбирает деньги и маржу, возвращает missing_skus."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/products/by-skus"
        return httpx.Response(
            200, json={"products": [_PRODUCT], "missing_skus": ["SKU-X"]}
        )

    fetch = await _client(handler).get_products_by_skus(("SKU-1",))

    assert fetch.products[0].price == Money.of("129.99", Currency("RUB"))
    assert fetch.products[0].margin_percent == Decimal("38.46")
    assert fetch.missing_skus == ("SKU-X",)


async def test_get_products_error_raises_catalog_unavailable() -> None:
    """Сетевая/HTTP-ошибка → CatalogUnavailable."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(CatalogUnavailable):
        await _client(handler).get_products_by_skus(("SKU-1",))


async def test_analyze_prices_parses_stats() -> None:
    """Анализ цен разбирается в статистики, бэнды и выбросы."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/analytics/prices"
        return httpx.Response(200, json=_ANALYSIS)

    result = await _client(handler).analyze_prices(
        ProductSelector(category="Аудио", price_min=Decimal("100")),
        bands=(
            MarginBandSpec(
                label="0-10%",
                lower_percent=Decimal("0"),
                upper_percent=Decimal("10"),
            ),
        ),
    )

    assert result.count == 42
    assert result.price.median == Decimal("900.00")
    assert result.margin.undefined_count == 1
    assert result.analysis_ref == "slice-1"
    assert result.bands[0].count == 12
    assert result.outliers[0].price == Money.of("9999.00", Currency("RUB"))
