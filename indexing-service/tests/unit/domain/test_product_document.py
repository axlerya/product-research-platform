"""Тесты сущности ``ProductDocument`` — поисковая проекция товара."""

from datetime import date
from decimal import Decimal

import pytest

from indexing_service.domain.entities.product_document import ProductDocument
from indexing_service.domain.exceptions import InvalidDocumentError
from indexing_service.domain.value_objects.currency import Currency
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.money import Money
from indexing_service.domain.value_objects.pricing import Pricing
from indexing_service.domain.value_objects.sku import Sku
from indexing_service.domain.value_objects.stock import StockLevel

RUB = Currency("RUB")


def _doc(**over) -> ProductDocument:
    fields = dict(
        product_id=ProductId.new(),
        sku=Sku("PROD-001"),
        name="Наушники",
        description="Беспроводные",
        category="Электроника",
        brand="AudioMax",
        supplier="TechSupply",
        pricing=Pricing(Money.of("129.99", RUB), Money.of("65.00", RUB)),
        stock=StockLevel(245),
        metrics=None,
        source_updated_at=date(2024, 3, 15),
        aggregate_version=1,
    )
    fields.update(over)
    return ProductDocument(**fields)


def test_search_text_composes_content_fields():
    text = _doc().search_text()
    assert "Товар: Наушники" in text.value
    assert "Бренд: AudioMax" in text.value


def test_margin_matches_pricing():
    assert _doc().margin().percent == Decimal("50.00")


def test_content_hash_changes_with_text():
    assert _doc().content_hash() != _doc(name="Другое").content_hash()


def test_content_hash_ignores_commercial_fields():
    # Цена/остаток не входят в текст → хэш эмбеддинга не меняется.
    base = _doc()
    commercial = _doc(
        pricing=Pricing(Money.of("99.99", RUB), Money.of("65.00", RUB)),
        stock=StockLevel(10),
    )
    assert base.content_hash() == commercial.content_hash()


def test_rejects_version_below_one():
    with pytest.raises(InvalidDocumentError):
        _doc(aggregate_version=0)


def test_rejects_blank_name():
    with pytest.raises(InvalidDocumentError):
        _doc(name="  ")
