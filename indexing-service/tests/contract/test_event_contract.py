"""Contract-тесты: consumer против контракта событий catalog (§11.4, §6.3).

Golden-примеры = wire-формат, который публикует catalog-service. Тест
краснеет ДО деплоя, если контракт (обязательные поля, деньги-строкой,
монотонная версия) нарушен или наш reader перестал их принимать.
"""

import json
from pathlib import Path

import pytest
from jsonschema import validate

from indexing_service.application.dto.events import (
    CommercialChangedEvent,
    ContentChangedEvent,
    ProductCreatedEvent,
    ProductDeletedEvent,
)
from indexing_service.presentation.messaging.parsing import parse_event
from indexing_service.presentation.messaging.schemas import CatalogEnvelope

pytestmark = pytest.mark.contract

_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = json.loads(
    (_ROOT / "contracts" / "consumer" / "envelope.schema.json").read_text(
        encoding="utf-8"
    )
)

_ALL = [
    "created",
    "content_changed",
    "commercial_data_changed",
    "deleted",
]


def _sample(name: str) -> dict:
    path = _ROOT / "contracts" / "samples" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", _ALL)
def test_sample_matches_envelope_schema(name):
    validate(instance=_sample(name), schema=_SCHEMA)


def test_created_full_snapshot_money_and_rating_as_strings():
    data = _sample("created")["data"]
    assert isinstance(data["price"]["amount"], str)
    assert isinstance(data["cost"]["amount"], str)
    assert isinstance(data["metrics"]["avg_rating"], str)
    assert {"name", "description", "category", "brand"} <= data.keys()


def test_content_changed_carries_full_text_group():
    # CDC: RAG эмбеддит name+description+category+brand — обязаны быть.
    data = _sample("content_changed")["data"]
    assert {"name", "description", "category", "brand"} <= data.keys()


def test_commercial_carries_price_cost_stock_as_string_money():
    data = _sample("commercial_data_changed")["data"]
    assert {"price", "cost", "stock", "supplier"} <= data.keys()
    assert isinstance(data["price"]["amount"], str)


@pytest.mark.parametrize(
    ("name", "dto"),
    [
        ("created", ProductCreatedEvent),
        ("content_changed", ContentChangedEvent),
        ("commercial_data_changed", CommercialChangedEvent),
        ("deleted", ProductDeletedEvent),
    ],
)
def test_parse_event_accepts_golden_samples(name, dto):
    event = parse_event(CatalogEnvelope.model_validate(_sample(name)))
    assert isinstance(event, dto)


def test_tolerant_reader_ignores_unknown_additive_fields():
    # MINOR-эволюция: новые поля в конверте и в data не ломают консюмер.
    sample = _sample("created")
    sample["schema_url"] = "https://schemas/catalog/created/1.1"
    sample["data"]["warranty_months"] = 24
    event = parse_event(CatalogEnvelope.model_validate(sample))
    assert isinstance(event, ProductCreatedEvent)
    assert event.product.sku == "PROD-001"
