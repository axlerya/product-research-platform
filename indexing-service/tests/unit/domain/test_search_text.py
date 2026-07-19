"""Тесты value object ``SearchText`` — составной текст для эмбеддинга."""

import pytest

from indexing_service.domain.exceptions import InvalidDocumentError
from indexing_service.domain.value_objects.search_text import SearchText


def test_holds_value():
    assert SearchText("Товар: Наушники").value == "Товар: Наушники"


def test_rejects_blank():
    with pytest.raises(InvalidDocumentError):
        SearchText("   ")


def test_equality_by_value():
    assert SearchText("a") == SearchText("a")
    assert SearchText("a") != SearchText("b")
