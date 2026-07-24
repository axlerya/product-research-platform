"""Тесты SourceValidator — provenance цитат (INV-2)."""

from datetime import UTC, datetime

from research_agent_service.application.services.source_validation import (
    SourceValidator,
)
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.enums import CitationType

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _citation(
    source_type: CitationType, ref: str, position: int = 0
) -> Citation:
    """Собирает цитату заданного типа и ссылки."""
    return Citation(
        source_type=source_type,
        ref=ref,
        title="заголовок",
        snippet="фрагмент",
        position=position,
        retrieved_at=_NOW,
    )


def test_keeps_citations_with_confirmed_provenance() -> None:
    """Цитаты с ref из соответствующего множества сохраняются."""
    citations = [
        _citation(CitationType.PRODUCT, "SKU-1"),
        _citation(CitationType.WEB, "https://a"),
        _citation(CitationType.PRICE_ANALYSIS, "slice-1"),
    ]

    result = SourceValidator().validate(
        citations,
        product_refs=frozenset({"SKU-1"}),
        web_refs=frozenset({"https://a"}),
        price_refs=frozenset({"slice-1"}),
    )

    assert len(result) == 3


def test_drops_dangling_product_citation() -> None:
    """Цитата на неизвестный sku отбрасывается."""
    result = SourceValidator().validate(
        [_citation(CitationType.PRODUCT, "SKU-UNKNOWN")],
        product_refs=frozenset({"SKU-1"}),
        web_refs=frozenset(),
        price_refs=frozenset(),
    )

    assert result == ()


def test_drops_on_type_mismatch() -> None:
    """ref сверяется с множеством своего типа, не чужого."""
    result = SourceValidator().validate(
        [_citation(CitationType.WEB, "SKU-1")],
        product_refs=frozenset({"SKU-1"}),
        web_refs=frozenset(),
        price_refs=frozenset(),
    )

    assert result == ()


def test_keeps_valid_drops_invalid_in_mixed_set() -> None:
    """Из смешанного набора остаются только подтверждённые цитаты."""
    valid = _citation(CitationType.PRODUCT, "SKU-1")
    invalid = _citation(CitationType.PRODUCT, "SKU-2", position=1)

    result = SourceValidator().validate(
        [valid, invalid],
        product_refs=frozenset({"SKU-1"}),
        web_refs=frozenset(),
        price_refs=frozenset(),
    )

    assert result == (valid,)


def test_empty_input_returns_empty() -> None:
    """Пустой вход даёт пустой результат."""
    result = SourceValidator().validate(
        [],
        product_refs=frozenset(),
        web_refs=frozenset(),
        price_refs=frozenset(),
    )

    assert result == ()
