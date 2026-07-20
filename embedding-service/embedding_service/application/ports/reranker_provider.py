"""Порт ``RerankerProvider`` — абстракция reranker-инференса.

Независим от FlagEmbedding/torch/CUDA/grpc. За портом скрыты загрузка модели,
executor, чанкинг и ограничение параллелизма. Отдельный порт от
``EmbeddingProvider`` — reranking полностью изолирован.
"""

from collections.abc import Sequence
from typing import Protocol

from embedding_service.application.dto.provider_status import ProviderStatus
from embedding_service.domain.value_objects.reranking.reranker_model_id import (
    RerankerModelId,
)


class RerankerProvider(Protocol):
    """Оценивает релевантность документов запросу (cross-encoder)."""

    @property
    def model_id(self) -> RerankerModelId:
        """Идентификатор текущей модели (== ``model_version`` на проводе)."""
        ...

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        """Возвращает скоры релевантности строго в порядке ``documents``."""
        ...

    async def warmup(self) -> None:
        """Прогрев: скорит проб-пару, проверяет форму выхода."""
        ...

    async def probe(self) -> ProviderStatus:
        """Возвращает статус без тяжёлого инференса (для readiness)."""
        ...
