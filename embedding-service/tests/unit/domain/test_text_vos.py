"""Unit-тесты текстовых/скалярных VO: EmbeddingText, TextId, EmbeddingKind,
TokenCount.
"""

import pytest

from embedding_service.domain.exceptions import (
    EmptyTextError,
    InvalidVectorError,
)
from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.domain.value_objects.text_id import TextId
from embedding_service.domain.value_objects.token_count import TokenCount


class TestEmbeddingText:
    def test_strips_and_reports_length(self) -> None:
        text = EmbeddingText("  привет мир  ")
        assert text.value == "привет мир"
        assert text.char_length == len("привет мир")

    @pytest.mark.parametrize("bad", ["", "   ", "\n\t "])
    def test_empty_or_blank_rejected(self, bad: str) -> None:
        with pytest.raises(EmptyTextError):
            EmbeddingText(bad)


class TestTextId:
    def test_preserves_value_verbatim(self) -> None:
        # id — ключ корреляции: не нормализуется (в отличие от текста).
        tid = TextId("  prod-42  ")
        assert tid.value == "  prod-42  "

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_empty_or_blank_rejected(self, bad: str) -> None:
        with pytest.raises(EmptyTextError):
            TextId(bad)


class TestEmbeddingKind:
    def test_two_kinds(self) -> None:
        assert {k.value for k in EmbeddingKind} == {"document", "query"}


class TestTokenCount:
    @pytest.mark.parametrize("value", [0, 1, 8192])
    def test_non_negative_allowed(self, value: int) -> None:
        assert TokenCount(value).value == value

    def test_negative_rejected(self) -> None:
        with pytest.raises(InvalidVectorError):
            TokenCount(-1)
