"""Тесты read-эндпоинтов HTTP API (TestClient + фейковые query-сервисы)."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from catalog_service.application.dto.queries import PriceAnalysisSelector
from catalog_service.application.dto.views import (
    CategoryMarginRow,
    MarginView,
    MoneyView,
    Page,
    ProductBatchView,
    ProductView,
    ReferenceView,
)
from catalog_service.application.price_analysis import AnalyzePrices
from catalog_service.presentation.api import deps
from catalog_service.presentation.api.app import create_app

_PID = UUID("0192f0c8-7b3a-7e2d-9a1c-000000000001")
_NOW = datetime(2026, 7, 19, tzinfo=UTC)


def _view(sku: str = "PROD-1") -> ProductView:
    return ProductView(
        id=_PID,
        sku=sku,
        name="Наушники",
        description="Опис",
        category="Электроника",
        brand="AudioMax",
        supplier="TechSupply Co",
        price=MoneyView(Decimal("129.99"), "RUB"),
        cost=MoneyView(Decimal("65.00"), "RUB"),
        stock=245,
        is_in_stock=True,
        sales_per_month=87,
        avg_rating=Decimal("4.50"),
        review_count=1243,
        margin=MarginView(MoneyView(Decimal("64.99"), "RUB"), Decimal("50.00")),
        source_updated_at=date(2024, 3, 15),
        version=1,
        is_deleted=False,
        created_at=_NOW,
        updated_at=_NOW,
    )


class _FakeProductQuery:
    def __init__(
        self, *, view=None, page=None, margins=(), batch=None, slice_=()
    ) -> None:
        self._view = view
        self._page = page
        self._margins = margins
        self._batch = batch
        self._slice = slice_
        self.calls: list = []

    async def get(self, *, product_id=None, sku=None, include_deleted=False):
        return self._view

    async def get_many(self, skus, *, include_deleted=False):
        self.calls.append((tuple(skus), include_deleted))
        return self._batch

    async def search(self, query):
        return self._page

    async def select_for_analysis(self, selector):
        self.calls.append(selector)
        return self._slice

    async def margin_by_category(self, *, include_deleted=False):
        return self._margins


class _FakeRefQuery:
    def __init__(self, refs=()) -> None:
        self._refs = refs

    async def list_categories(self):
        return self._refs

    async def list_brands(self):
        return self._refs

    async def list_suppliers(self):
        return self._refs


def _make(impl):
    def _provider():
        return impl

    return _provider


def _client(overrides: dict) -> TestClient:
    app = create_app()
    for provider, impl in overrides.items():
        app.dependency_overrides[provider] = _make(impl)
    return TestClient(app)


def test_get_product_returns_read():
    qs = _FakeProductQuery(view=_view())
    client = _client({deps.get_product_query_service: qs})
    resp = client.get(f"/api/v1/products/{_PID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sku"] == "PROD-1"
    assert body["price"] == {"amount": "129.99", "currency": "RUB"}
    assert body["margin"]["percent"] == "50.00"
    assert body["is_in_stock"] is True


def test_get_product_not_found_returns_404():
    qs = _FakeProductQuery(view=None)
    client = _client({deps.get_product_query_service: qs})
    resp = client.get(f"/api/v1/products/{_PID}")
    assert resp.status_code == 404
    assert resp.json()["code"] == "product_not_found"


def test_get_by_sku_returns_read():
    qs = _FakeProductQuery(view=_view("PROD-9"))
    client = _client({deps.get_product_query_service: qs})
    resp = client.get("/api/v1/products/by-sku/PROD-9")
    assert resp.status_code == 200
    assert resp.json()["sku"] == "PROD-9"


def test_by_sku_not_found_returns_404():
    qs = _FakeProductQuery(view=None)
    client = _client({deps.get_product_query_service: qs})
    resp = client.get("/api/v1/products/by-sku/NOPE-1")
    assert resp.status_code == 404


def test_search_returns_page():
    qs = _FakeProductQuery(
        page=Page(items=(_view(),), total=1, limit=20, offset=0)
    )
    client = _client({deps.get_product_query_service: qs})
    resp = client.get(
        "/api/v1/products?category=Электроника&margin_max=90&in_stock=true"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["sku"] == "PROD-1"


def test_get_margin_returns_read():
    qs = _FakeProductQuery(view=_view())
    client = _client({deps.get_product_query_service: qs})
    resp = client.get(f"/api/v1/products/{_PID}/margin")
    assert resp.status_code == 200
    assert resp.json()["percent"] == "50.00"
    assert resp.json()["profit"] == {"amount": "64.99", "currency": "RUB"}


def test_margin_not_found_returns_404():
    qs = _FakeProductQuery(view=None)
    client = _client({deps.get_product_query_service: qs})
    resp = client.get(f"/api/v1/products/{_PID}/margin")
    assert resp.status_code == 404


def test_list_categories_returns_references():
    refs = (ReferenceView(id=_PID, name="Электроника", product_count=3),)
    qs = _FakeRefQuery(refs)
    client = _client({deps.get_reference_query_service: qs})
    for path in ("/categories", "/brands", "/suppliers"):
        resp = client.get(f"/api/v1{path}")
        assert resp.status_code == 200
        assert resp.json()[0] == {
            "id": str(_PID),
            "name": "Электроника",
            "product_count": 3,
        }


def test_analytics_margin_returns_rows():
    rows = (
        CategoryMarginRow(
            category="Электроника",
            product_count=2,
            avg_margin_percent=Decimal("50.00"),
            min_margin_percent=Decimal("25.00"),
            max_margin_percent=Decimal("75.00"),
        ),
    )
    qs = _FakeProductQuery(margins=rows)
    client = _client({deps.get_product_query_service: qs})
    resp = client.get("/api/v1/analytics/margin")
    assert resp.status_code == 200
    assert resp.json()[0]["category"] == "Электроника"
    assert resp.json()[0]["avg_margin_percent"] == "50.00"


def test_by_skus_returns_found_and_missing():
    batch = ProductBatchView(
        products=(_view("PROD-1"),), missing_skus=("NOPE-1",)
    )
    qs = _FakeProductQuery(batch=batch)
    client = _client({deps.get_product_query_service: qs})
    resp = client.post(
        "/api/v1/products/by-skus",
        json={"skus": ["PROD-1", "NOPE-1"], "include_deleted": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["missing_skus"] == ["NOPE-1"]
    assert body["products"][0]["sku"] == "PROD-1"
    assert body["products"][0]["price"] == {
        "amount": "129.99",
        "currency": "RUB",
    }
    assert body["products"][0]["margin"]["percent"] == "50.00"
    assert qs.calls == [(("PROD-1", "NOPE-1"), False)]


def test_by_skus_passes_include_deleted():
    qs = _FakeProductQuery(batch=ProductBatchView(products=(), missing_skus=()))
    client = _client({deps.get_product_query_service: qs})
    resp = client.post(
        "/api/v1/products/by-skus",
        json={"skus": ["PROD-1"], "include_deleted": True},
    )
    assert resp.status_code == 200
    assert qs.calls == [(("PROD-1",), True)]


def test_by_skus_without_skus_returns_empty_batch():
    qs = _FakeProductQuery(batch=ProductBatchView(products=(), missing_skus=()))
    client = _client({deps.get_product_query_service: qs})
    resp = client.post("/api/v1/products/by-skus", json={"skus": []})
    assert resp.status_code == 200
    assert resp.json() == {"products": [], "missing_skus": []}


def test_by_skus_rejects_unknown_field():
    qs = _FakeProductQuery(batch=ProductBatchView(products=(), missing_skus=()))
    client = _client({deps.get_product_query_service: qs})
    resp = client.post(
        "/api/v1/products/by-skus", json={"skus": [], "limit": 5}
    )
    assert resp.status_code == 422


def test_analytics_prices_returns_statistics():
    qs = _FakeProductQuery(slice_=(_view("PROD-1"), _view("PROD-2")))
    uc = AnalyzePrices(products=qs, default_currency="RUB")
    client = _client({deps.get_analyze_prices: uc})
    resp = client.post(
        "/api/v1/analytics/prices",
        json={
            "selector": {"category": "Электроника", "skus": []},
            "bands": [{"label": "высокая", "lower_percent": "40"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["currency"] == "RUB"
    assert body["price"]["median"] == "129.99"
    assert body["price"]["stddev"] == "0.00"
    assert body["margin"]["median_percent"] == "50.00"
    assert body["margin"]["undefined_count"] == 0
    assert body["bands"] == [
        {
            "label": "высокая",
            "count": 2,
            "lower_percent": "40.00",
            "upper_percent": None,
        }
    ]
    assert body["outliers"] == []
    assert body["analysis_ref"].startswith("pa-")
    assert qs.calls[0].category == "Электроника"


def test_analytics_prices_defaults_to_whole_catalog():
    qs = _FakeProductQuery(slice_=())
    uc = AnalyzePrices(products=qs, default_currency="RUB")
    client = _client({deps.get_analyze_prices: uc})
    resp = client.post("/api/v1/analytics/prices", json={})
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
    assert qs.calls[0] == PriceAnalysisSelector()


def test_analytics_prices_rejects_mixed_currency_slice():
    usd = replace(_view("PROD-2"), price=MoneyView(Decimal("10.00"), "USD"))
    qs = _FakeProductQuery(slice_=(_view("PROD-1"), usd))
    uc = AnalyzePrices(products=qs, default_currency="RUB")
    client = _client({deps.get_analyze_prices: uc})
    resp = client.post("/api/v1/analytics/prices", json={})
    assert resp.status_code == 409
    assert resp.json()["code"] == "mixed_currency_slice"


@pytest.mark.parametrize(
    "provider",
    [
        deps.get_product_query_service,
        deps.get_reference_query_service,
        deps.get_analyze_prices,
    ],
)
def test_query_providers_are_unwired(provider):
    with pytest.raises(NotImplementedError):
        provider()
