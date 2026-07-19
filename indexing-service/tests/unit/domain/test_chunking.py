"""Тесты стратегии чанкинга ``SingleDocument`` (одна точка на товар)."""

from indexing_service.domain.services.chunking import SingleDocument
from indexing_service.domain.value_objects.search_text import SearchText


def test_single_document_returns_one_chunk():
    text = SearchText("Товар: X")
    assert SingleDocument().chunk(text) == [text]
