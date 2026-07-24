"""Тесты контрактов аргументов инструментов агента."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from research_agent_service.infrastructure.agent.contracts import (
    MarginBandArg,
    PriceAnalysisArgs,
    ProductCatalogRagArgs,
    WebSearchArgs,
)


def test_rag_args_without_facets_yield_no_filters() -> None:
    """Только запрос → фильтров нет."""
    args = ProductCatalogRagArgs(query="наушники")
    assert args.to_filters() is None


def test_rag_args_with_facets_build_filters() -> None:
    """Заданные фасеты → QueryFilters с приведением к Decimal."""
    args = ProductCatalogRagArgs(
        query="наушники",
        category="Аудио",
        in_stock=True,
        price_min=10,
        price_max="99.90",
    )
    filters = args.to_filters()

    assert filters is not None
    assert filters.category == "Аудио"
    assert filters.in_stock is True
    assert filters.price_min == Decimal("10")
    assert filters.price_max == Decimal("99.90")


def test_rag_args_reject_unknown_fields() -> None:
    """extra='forbid': лишние поля от модели отклоняются."""
    with pytest.raises(ValidationError):
        ProductCatalogRagArgs(query="q", sql="DROP TABLE")


def test_price_args_build_selector_and_bands() -> None:
    """Селектор и бэнды переводятся в DTO прикладного слоя."""
    args = PriceAnalysisArgs(
        skus=["SKU-1", "SKU-2"],
        category="Аудио",
        in_stock=True,
        bands=[MarginBandArg(label="низкая", upper_percent=10)],
    )
    selector = args.to_selector()
    bands = args.to_bands()

    assert selector.skus == ("SKU-1", "SKU-2")
    assert selector.category == "Аудио"
    assert selector.in_stock is True
    assert len(bands) == 1
    assert bands[0].label == "низкая"
    assert bands[0].upper_percent == Decimal("10")


def test_price_args_default_empty() -> None:
    """Без аргументов селектор пуст, бэндов нет."""
    args = PriceAnalysisArgs()
    assert args.to_selector().skus == ()
    assert args.to_bands() == ()


def test_margin_band_to_spec() -> None:
    """MarginBandArg → MarginBandSpec."""
    spec = MarginBandArg(
        label="средняя", lower_percent=10, upper_percent=20
    ).to_spec()
    assert spec.label == "средняя"
    assert spec.lower_percent == Decimal("10")
    assert spec.upper_percent == Decimal("20")


def test_web_args_defaults_and_bounds() -> None:
    """k по умолчанию 5, вне диапазона — ошибка валидации."""
    assert WebSearchArgs(query="q").k == 5
    assert WebSearchArgs(query="q", k=10).k == 10
    with pytest.raises(ValidationError):
        WebSearchArgs(query="q", k=0)
    with pytest.raises(ValidationError):
        WebSearchArgs(query="q", k=11)
