"""Тесты value object Citation — проверяемого источника факта."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from research_agent_service.domain.exceptions import (
    DomainError,
    InvalidCitation,
)
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.enums import CitationType


def _citation(**overrides: object) -> Citation:
    """Собирает валидную Citation с точечными переопределениями."""
    fields: dict[str, object] = {
        "source_type": CitationType.PRODUCT,
        "ref": "SKU-123",
        "title": "Наушники",
        "snippet": "Беспроводные наушники",
        "position": 0,
        "retrieved_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return Citation(**fields)  # type: ignore[arg-type]


def test_valid_citation_holds_fields() -> None:
    """Валидная Citation сохраняет все поля; score по умолчанию None."""
    citation = _citation(score=Decimal("0.94"))

    assert citation.source_type is CitationType.PRODUCT
    assert citation.ref == "SKU-123"
    assert citation.score == Decimal("0.94")


def test_score_is_optional() -> None:
    """score необязателен (web-источник без скоринга)."""
    assert _citation().score is None


def test_blank_ref_is_rejected() -> None:
    """Пустой ref недопустим: цитата обязана ссылаться на факт."""
    with pytest.raises(InvalidCitation):
        _citation(ref="   ")


def test_negative_position_is_rejected() -> None:
    """Позиция цитаты не может быть отрицательной."""
    with pytest.raises(InvalidCitation):
        _citation(position=-1)


def test_invalid_citation_is_domain_error() -> None:
    """InvalidCitation — доменное исключение."""
    assert issubclass(InvalidCitation, DomainError)


def test_citation_is_frozen() -> None:
    """Citation неизменяема."""
    citation = _citation()

    with pytest.raises(FrozenInstanceError):
        citation.ref = "SKU-999"
