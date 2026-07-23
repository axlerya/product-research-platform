"""Стратегии чанкинга. По умолчанию — одна точка на товар (§5.2)."""

from collections.abc import Sequence
from typing import Protocol

from indexing_service.domain.exceptions import InvalidDocumentError
from indexing_service.domain.value_objects.search_text import SearchText

# Разделители от крупного к мелкому: абзац → строка → предложение → слово.
DEFAULT_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", " ")


class ChunkingStrategy(Protocol):
    """Политика разбиения документа на чанки для эмбеддинга."""

    def chunk(self, text: SearchText) -> list[SearchText]:
        """Разбивает текст на чанки (каждый эмбеддится отдельно)."""
        ...


class SingleDocument:
    """Без разбиения: весь документ — один чанк (одна точка Qdrant)."""

    def chunk(self, text: SearchText) -> list[SearchText]:
        """Возвращает единственный чанк — исходный текст."""
        return [text]


class RecursiveChunker:
    """Дробит текст рекурсивно по убывающим разделителям (§5.3).

    Режет по самому крупному разделителю, куски длиннее лимита — по более
    мелкому, и так далее; текст без разделителей режется по символам.
    Соседние мелкие куски склеиваются обратно, пока влезают в лимит.
    """

    def __init__(
        self,
        *,
        max_chars: int,
        separators: Sequence[str] = DEFAULT_SEPARATORS,
    ) -> None:
        if max_chars < 1:
            raise InvalidDocumentError(f"max_chars < 1: {max_chars}")
        self._max_chars = max_chars
        self._separators = tuple(separators)

    def chunk(self, text: SearchText) -> list[SearchText]:
        """Разбивает текст на куски не длиннее ``max_chars``."""
        pieces = self._split(text.value.strip(), self._separators)
        return [SearchText(piece) for piece in pieces if piece.strip()]

    def _split(self, text: str, separators: tuple[str, ...]) -> list[str]:
        if len(text) <= self._max_chars:
            return [text]
        if not separators:
            step = self._max_chars
            return [text[i : i + step] for i in range(0, len(text), step)]
        separator, rest = separators[0], separators[1:]
        if separator not in text:
            return self._split(text, rest)
        pieces: list[str] = []
        for part in text.split(separator):
            if part:
                pieces.extend(self._split(part, rest))
        return self._merge(pieces, separator)

    def _merge(self, pieces: list[str], separator: str) -> list[str]:
        """Склеивает соседние куски, пока сумма влезает в лимит."""
        merged: list[str] = []
        for piece in pieces:
            if merged and (
                len(merged[-1]) + len(separator) + len(piece)
                <= self._max_chars
            ):
                merged[-1] = f"{merged[-1]}{separator}{piece}"
            else:
                merged.append(piece)
        return merged


def split_oversize(text: SearchText) -> list[SearchText]:
    """Дробит текст, не влезший в лимит модели (Q2 §8).

    Точный лимит embedding-service нам неизвестен — ошибка
    ``TOKENS_EXCEEDED``/``TEXT_TOO_LONG`` его не сообщает. Поэтому режем
    примерно пополам: за несколько раундов текст гарантированно уместится.

    Returns:
        Не менее двух кусков либо пустой список, если дробить уже некуда.
    """
    value = text.value.strip()
    if len(value) < 2:
        return []
    chunker = RecursiveChunker(max_chars=len(value) // 2)
    pieces = chunker.chunk(SearchText(value))
    return pieces if len(pieces) > 1 else []
