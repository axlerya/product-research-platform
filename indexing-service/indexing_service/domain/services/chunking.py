"""Стратегии чанкинга. По умолчанию — одна точка на товар (§5.2)."""

from typing import Protocol

from indexing_service.domain.value_objects.search_text import SearchText


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
