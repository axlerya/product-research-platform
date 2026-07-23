"""Тесты стратегий чанкинга: ``SingleDocument`` и ``RecursiveChunker``."""

import pytest

from indexing_service.domain.exceptions import InvalidDocumentError
from indexing_service.domain.services.chunking import (
    RecursiveChunker,
    SingleDocument,
    split_oversize,
)
from indexing_service.domain.value_objects.search_text import SearchText


def test_single_document_returns_one_chunk():
    text = SearchText("Товар: X")
    assert SingleDocument().chunk(text) == [text]


def _values(chunks: list[SearchText]) -> list[str]:
    return [chunk.value for chunk in chunks]


def test_short_text_stays_whole():
    text = SearchText("Кружка керамическая")
    assert RecursiveChunker(max_chars=100).chunk(text) == [text]


def test_splits_by_paragraphs_first():
    text = SearchText("первый абзац\n\nвторой абзац\n\nтретий абзац")
    chunks = RecursiveChunker(max_chars=15).chunk(text)
    assert _values(chunks) == ["первый абзац", "второй абзац", "третий абзац"]


def test_falls_through_to_smaller_separators():
    text = SearchText("раз два три четыре пять шесть")
    chunks = RecursiveChunker(max_chars=12).chunk(text)
    assert all(len(chunk.value) <= 12 for chunk in chunks)
    assert " ".join(_values(chunks)) == text.value


def test_text_without_separators_is_cut_by_chars():
    text = SearchText("абвгдеёжзи")
    chunks = RecursiveChunker(max_chars=4).chunk(text)
    assert _values(chunks) == ["абвг", "деёж", "зи"]


def test_adjacent_small_pieces_are_merged_back():
    text = SearchText("а\n\nб\n\nв\n\nг")
    chunks = RecursiveChunker(max_chars=5).chunk(text)
    # склеиваем, пока влезает: "а\n\nб" (4) + "в" не влезет (7) → два куска
    assert len(chunks) < 4
    assert all(len(chunk.value) <= 5 for chunk in chunks)


def test_max_chars_must_be_positive():
    with pytest.raises(InvalidDocumentError):
        RecursiveChunker(max_chars=0)


def test_split_oversize_halves_text():
    text = SearchText("раз два три четыре пять шесть семь восемь")
    pieces = split_oversize(text)

    assert len(pieces) > 1
    assert " ".join(_values(pieces)) == text.value
    # каждый кусок заметно короче исходного — дробление прогрессирует
    assert all(len(p.value) < len(text.value) for p in pieces)


def test_split_oversize_without_separators_still_splits():
    pieces = split_oversize(SearchText("абвгдеёжзи"))
    assert _values(pieces) == ["абвгд", "еёжзи"]


def test_split_oversize_gives_up_on_single_char():
    assert split_oversize(SearchText("я")) == []
