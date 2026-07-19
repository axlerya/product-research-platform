"""Порт ``EmbeddingModel`` — абстракция эмбеддера (BGE-M3)."""

from collections.abc import Sequence
from typing import Protocol

from indexing_service.domain.value_objects.embedding import Embedding
from indexing_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from indexing_service.domain.value_objects.search_text import SearchText


class EmbeddingModel(Protocol):
    """Строит dense + sparse эмбеддинги из текстов документов."""

    @property
    def model_id(self) -> EmbeddingModelId:
        """Идентификатор текущей модели (для payload и детекта смены)."""
        ...

    async def embed_documents(
        self, texts: Sequence[SearchText]
    ) -> list[Embedding]:
        """Возвращает эмбеддинги в порядке входных текстов."""
        ...
