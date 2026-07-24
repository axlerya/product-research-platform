"""Тесты value objects Query и QueryFilters (валидация входа)."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from research_agent_service.domain.exceptions import (
    DomainError,
    EmptyQuery,
    InvalidQuery,
    QueryTooLong,
)
from research_agent_service.domain.value_objects.query import (
    MAX_QUERY_CHARS,
    Query,
    QueryFilters,
)


def test_valid_query_strips_text_and_applies_defaults() -> None:
    """Текст обрезается по краям; locale/filters/idempotency — по умолчанию."""
    query = Query(text="  найди наушники  ")

    assert query.text == "найди наушники"
    assert query.locale == "ru"
    assert query.filters is None
    assert query.idempotency_key is None


def test_empty_text_raises_empty_query() -> None:
    """Пустой (или из пробелов) запрос недопустим."""
    with pytest.raises(EmptyQuery):
        Query(text="   ")


def test_too_long_text_raises_query_too_long() -> None:
    """Запрос длиннее лимита недопустим."""
    with pytest.raises(QueryTooLong):
        Query(text="x" * (MAX_QUERY_CHARS + 1))


def test_query_exception_hierarchy() -> None:
    """EmptyQuery/QueryTooLong — частные случаи InvalidQuery (DomainError)."""
    assert issubclass(EmptyQuery, InvalidQuery)
    assert issubclass(QueryTooLong, InvalidQuery)
    assert issubclass(InvalidQuery, DomainError)


def test_query_is_frozen() -> None:
    """Query неизменяем."""
    query = Query(text="привет")

    with pytest.raises(FrozenInstanceError):
        query.text = "пока"


def test_filters_hold_facets() -> None:
    """QueryFilters сохраняет заданные фасеты."""
    filters = QueryFilters(
        category="Наушники",
        price_max=Decimal("5000"),
        in_stock=True,
    )

    assert filters.category == "Наушники"
    assert filters.price_max == Decimal("5000")
    assert filters.in_stock is True


def test_empty_filters_are_valid() -> None:
    """Пустые фильтры допустимы (все поля None)."""
    assert QueryFilters().category is None


def test_price_min_greater_than_max_is_rejected() -> None:
    """price_min не может быть больше price_max."""
    with pytest.raises(InvalidQuery):
        QueryFilters(price_min=Decimal("100"), price_max=Decimal("50"))


def test_margin_min_greater_than_max_is_rejected() -> None:
    """margin_min не может быть больше margin_max."""
    with pytest.raises(InvalidQuery):
        QueryFilters(margin_min=Decimal("30"), margin_max=Decimal("10"))
