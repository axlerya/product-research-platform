"""Порт ``Tokenizer`` — опциональный подсчёт/усечение токенов."""

from typing import Protocol

from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.domain.value_objects.token_count import TokenCount


class Tokenizer(Protocol):
    """Токенайзер модели (для строгого токен-лимита и усечения)."""

    def count_tokens(self, text: EmbeddingText) -> TokenCount:
        """Возвращает число токенов текста."""
        ...

    def truncate(
        self, text: EmbeddingText, max_tokens: int
    ) -> tuple[EmbeddingText, TokenCount, bool]:
        """Усекает текст до ``max_tokens``; возвращает ``(текст, счётчик,
        был_ли_усечён)``.
        """
        ...
