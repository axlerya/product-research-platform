"""Контракт REST каталога, от которого зависит research-agent-service.

Схемы описывают ровно то, что читает ``HttpCatalogClient``. Проверяются на
живом каталоге стенда: расхождение здесь означает, что агент на этих данных
уйдёт в деградацию или упадёт.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.support.stand import Catalog, unique_suffix

pytestmark = pytest.mark.contract

_CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "catalog"


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((_CONTRACTS / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


@pytest.fixture
def slice_products(catalog: Catalog) -> tuple[str, list[str]]:
    """Три товара своей категории с известными ценами и маржой."""
    suffix = unique_suffix()
    category = f"E2ECAT-{suffix}"
    prices = (("100.00", "40.00"), ("200.00", "150.00"), ("300.00", "60.00"))
    skus = []
    for index, (price, cost) in enumerate(prices, start=1):
        sku = f"E2E-{suffix}-{index}"
        catalog.create(
            sku=sku,
            name=f"Контрактный товар {index} {suffix}",
            description="Товар контрактной проверки каталога.",
            category=category,
            price=price,
            cost=cost,
        )
        skus.append(sku)
    return category, skus


def test_by_skus_matches_agent_contract(
    catalog: Catalog, slice_products: tuple[str, list[str]]
) -> None:
    """Ответ batch-чтения удовлетворяет схеме, которую читает агент."""
    _, skus = slice_products
    response = catalog.by_skus([*skus, "NOSUCH-SKU-1"])

    assert response.status_code == 200
    body = response.json()
    _validator("products_by_skus.schema.json").validate(body)
    assert body["missing_skus"] == ["NOSUCH-SKU-1"]
    assert [item["sku"] for item in body["products"]] == skus


def test_by_skus_money_parses_as_decimal(
    catalog: Catalog, slice_products: tuple[str, list[str]]
) -> None:
    """Деньги приходят строкой и разбираются без потери точности."""
    _, skus = slice_products
    product = catalog.by_skus(skus[:1]).json()["products"][0]

    assert Decimal(product["price"]["amount"]) == Decimal("100.00")
    assert Decimal(product["margin"]["percent"]) == Decimal("60.00")


def test_price_analysis_matches_agent_contract(
    catalog: Catalog, slice_products: tuple[str, list[str]]
) -> None:
    """Ответ ценового анализа удовлетворяет схеме, которую читает агент."""
    category, _ = slice_products
    response = catalog.analyze_prices(
        {"category": category},
        [
            {"label": "низкая", "upper_percent": "30"},
            {"label": "высокая", "lower_percent": "30"},
        ],
    )

    assert response.status_code == 200
    body = response.json()
    _validator("price_analysis.schema.json").validate(body)
    assert body["count"] == 3
    assert body["currency"] == "RUB"
    assert Decimal(body["price"]["median"]) == Decimal("200.00")
    # Маржи 60.00 / 25.00 / 80.00 — один товар в нижнем бэнде, два в верхнем.
    assert [band["count"] for band in body["bands"]] == [1, 2]


def test_price_analysis_selects_by_skus(
    catalog: Catalog, slice_products: tuple[str, list[str]]
) -> None:
    """Явный список артикулов сужает срез до перечисленных товаров."""
    _, skus = slice_products
    body = catalog.analyze_prices({"skus": skus[:2]}).json()

    assert body["count"] == 2
    assert Decimal(body["price"]["max"]) == Decimal("200.00")


def test_price_analysis_on_empty_slice_is_total(catalog: Catalog) -> None:
    """Пустой срез не ломает контракт: нули и валидный analysis_ref."""
    body = catalog.analyze_prices({"category": f"NOSUCH-{unique_suffix()}"})

    assert body.status_code == 200
    _validator("price_analysis.schema.json").validate(body.json())
    assert body.json()["count"] == 0
