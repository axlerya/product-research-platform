"""Порт ``EmbeddingProvider`` — ключевая абстракция инференса.

Независим от FlagEmbedding/torch/CUDA/grpc/faststream. За портом скрыты
загрузка модели, executor, micro-batching и backpressure.
"""

from collections.abc import Sequence
from typing import Protocol

from embedding_service.application.dto.provider_status import ProviderStatus
from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.embedding_text import EmbeddingText


class EmbeddingProvider(Protocol):
    """Строит dense + sparse эмбеддинги из текстов."""

    @property
    def model_id(self) -> EmbeddingModelId:
        """Идентификатор текущей модели (== ``model_version`` на проводе)."""
        ...

    async def embed(
        self, texts: Sequence[EmbeddingText], *, kind: EmbeddingKind
    ) -> list[Embedding]:
        """Возвращает эмбеддинги строго в порядке входных текстов."""
        ...

    async def warmup(self) -> None:
        """Прогрев: энкодит проб-текст, проверяет форму выхода."""
        ...

    async def probe(self) -> ProviderStatus:
        """Возвращает статус без тяжёлого инференса (для readiness)."""
        ...
