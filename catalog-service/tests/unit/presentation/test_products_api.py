"""Тесты HTTP API товаров (TestClient + фейковые use cases)."""

from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from catalog_service.application.dto.commands import CommandResult
from catalog_service.application.exceptions import (
    BusinessRuleViolation,
    CatalogError,
    ConcurrencyConflict,
    DuplicateSku,
    ProductNotFound,
    ValidationError,
)
from catalog_service.presentation.api import deps
from catalog_service.presentation.api.app import create_app

_PID = UUID("0192f0c8-7b3a-7e2d-9a1c-000000000001")
_CREATE_BODY = {
    "sku": "PROD-1",
    "name": "Наушники",
    "category": "Электроника",
    "brand": "AudioMax",
    "supplier": "TechSupply Co",
    "price": "129.99",
    "cost": "65.00",
    "stock": 245,
}


class _FakeUC:
    def __init__(self, *, result=None, exc=None) -> None:
        self._result = result
        self._exc = exc
        self.received = None

    async def execute(self, cmd):
        self.received = cmd
        if self._exc is not None:
            raise self._exc
        return self._result


def _result(version: int = 1, sku: str = "PROD-1") -> CommandResult:
    return CommandResult(
        product_id=_PID, sku=sku, version=version, emitted_events=()
    )


def _make_provider(uc):
    def _provider():
        return uc

    return _provider


def _client(overrides: dict) -> TestClient:
    app = create_app()
    for provider, uc in overrides.items():
        app.dependency_overrides[provider] = _make_provider(uc)
    return TestClient(app)


def test_create_returns_201_with_headers():
    uc = _FakeUC(result=_result())
    client = _client({deps.get_create_product_uc: uc})
    resp = client.post("/api/v1/products", json=_CREATE_BODY)
    assert resp.status_code == 201
    assert resp.json() == {"id": str(_PID), "sku": "PROD-1", "version": 1}
    assert resp.headers["ETag"] == '"1"'
    assert resp.headers["Location"] == f"/api/v1/products/{_PID}"
    assert uc.received.price_amount == Decimal("129.99")


def test_create_invalid_sku_returns_422_problem():
    uc = _FakeUC(result=_result())
    client = _client({deps.get_create_product_uc: uc})
    resp = client.post("/api/v1/products", json={**_CREATE_BODY, "sku": "!!"})
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["code"] == "validation_error"


def test_create_duplicate_returns_409():
    uc = _FakeUC(exc=DuplicateSku("дубль", meta={"sku": "PROD-1"}))
    client = _client({deps.get_create_product_uc: uc})
    resp = client.post("/api/v1/products", json=_CREATE_BODY)
    assert resp.status_code == 409
    assert resp.json()["code"] == "duplicate_sku"
    assert resp.json()["meta"] == {"sku": "PROD-1"}


def test_domain_validation_error_returns_422():
    uc = _FakeUC(exc=ValidationError("отрицательная цена"))
    client = _client({deps.get_create_product_uc: uc})
    resp = client.post("/api/v1/products", json=_CREATE_BODY)
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_business_rule_violation_returns_400():
    uc = _FakeUC(exc=BusinessRuleViolation("нельзя"))
    client = _client({deps.get_create_product_uc: uc})
    resp = client.post("/api/v1/products", json=_CREATE_BODY)
    assert resp.status_code == 400
    assert resp.json()["code"] == "business_rule_violation"


def test_generic_catalog_error_returns_400():
    uc = _FakeUC(exc=CatalogError("что-то пошло не так"))
    client = _client({deps.get_create_product_uc: uc})
    resp = client.post("/api/v1/products", json=_CREATE_BODY)
    assert resp.status_code == 400


def test_patch_content_requires_if_match_428():
    uc = _FakeUC(result=_result(version=2))
    client = _client({deps.get_update_content_uc: uc})
    resp = client.patch(f"/api/v1/products/{_PID}", json={"name": "Новое"})
    assert resp.status_code == 428


def test_patch_content_malformed_if_match_400():
    uc = _FakeUC(result=_result(version=2))
    client = _client({deps.get_update_content_uc: uc})
    resp = client.patch(
        f"/api/v1/products/{_PID}",
        json={"name": "Новое"},
        headers={"If-Match": "garbage"},
    )
    assert resp.status_code == 400


def test_patch_content_with_if_match_returns_200():
    uc = _FakeUC(result=_result(version=2))
    client = _client({deps.get_update_content_uc: uc})
    resp = client.patch(
        f"/api/v1/products/{_PID}",
        json={"name": "Новое"},
        headers={"If-Match": '"1"'},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 2
    assert resp.headers["ETag"] == '"2"'
    assert uc.received.expected_version == 1


def test_patch_stale_version_returns_409():
    uc = _FakeUC(exc=ConcurrencyConflict("конфликт", meta={"sku": "PROD-1"}))
    client = _client({deps.get_update_content_uc: uc})
    resp = client.patch(
        f"/api/v1/products/{_PID}",
        json={"name": "X"},
        headers={"If-Match": '"1"'},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "concurrency_conflict"


def test_commercial_not_found_returns_404():
    uc = _FakeUC(exc=ProductNotFound("нет товара"))
    client = _client({deps.get_update_commercial_uc: uc})
    resp = client.patch(
        f"/api/v1/products/{_PID}/commercial",
        json={"price": "99.99"},
        headers={"If-Match": '"3"'},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "product_not_found"


def test_commercial_success_returns_200():
    uc = _FakeUC(result=_result(version=2))
    client = _client({deps.get_update_commercial_uc: uc})
    resp = client.patch(
        f"/api/v1/products/{_PID}/commercial",
        json={"price": "119.99"},
        headers={"If-Match": '"1"'},
    )
    assert resp.status_code == 200
    assert uc.received.price_amount == Decimal("119.99")


def test_set_stock_returns_200():
    uc = _FakeUC(result=_result(version=2))
    client = _client({deps.get_set_stock_uc: uc})
    resp = client.patch(
        f"/api/v1/products/{_PID}/stock",
        json={"stock": 300},
        headers={"If-Match": '"1"'},
    )
    assert resp.status_code == 200
    assert uc.received.stock_quantity == 300


def test_update_metrics_returns_200():
    uc = _FakeUC(result=_result(version=2))
    client = _client({deps.get_update_metrics_uc: uc})
    resp = client.patch(
        f"/api/v1/products/{_PID}/metrics",
        json={
            "sales_per_month": 10,
            "avg_rating": "4.5",
            "review_count": 5,
        },
        headers={"If-Match": '"1"'},
    )
    assert resp.status_code == 200


def test_delete_returns_204():
    uc = _FakeUC(result=_result())
    client = _client({deps.get_delete_product_uc: uc})
    resp = client.delete(
        f"/api/v1/products/{_PID}", headers={"If-Match": '"1"'}
    )
    assert resp.status_code == 204
    assert uc.received.expected_version == 1


def test_health_and_ready():
    client = _client({})
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}


@pytest.mark.parametrize(
    "provider",
    [
        deps.get_create_product_uc,
        deps.get_update_content_uc,
        deps.get_update_commercial_uc,
        deps.get_set_stock_uc,
        deps.get_update_metrics_uc,
        deps.get_delete_product_uc,
    ],
)
def test_providers_are_unwired(provider):
    with pytest.raises(NotImplementedError):
        provider()
