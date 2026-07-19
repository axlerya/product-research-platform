"""Детерминированный эмбеддер для FAKE-режима.

Позволяет прогнать конвейер (docker-compose, smoke) без загрузки BGE-M3.
Векторы выводятся из sha256 текста — стабильны, но не семантичны.
"""

import hashlib
from collections.abc import Sequence

from indexing_service.domain.value_objects.dense_vector import DenseVector
from indexing_service.domain.value_objects.embedding import Embedding
from indexing_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from indexing_service.domain.value_objects.search_text import SearchText
from indexing_service.domain.value_objects.sparse_vector import SparseVector


class DeterministicEmbeddingModel:
    """Хэш-эмбеддер фиксированной размерности (не для продакшена)."""

    def __init__(self, *, dim: int = 8) -> None:
        self._dim = dim
        self._model_id = EmbeddingModelId(
            name="deterministic",
            revision="v1",
            pooling="hash",
            normalized=False,
            dim=dim,
        )

    @property
    def model_id(self) -> EmbeddingModelId:
        return self._model_id

    async def embed_documents(
        self, texts: Sequence[SearchText]
    ) -> list[Embedding]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: SearchText) -> Embedding:
        digest = hashlib.sha256(text.value.encode("utf-8")).digest()
        dense = DenseVector(
            tuple(digest[i % len(digest)] / 255.0 for i in range(self._dim))
        )
        weights = {
            int(digest[i]) + 1: (digest[i] + 1) / 256.0 for i in range(4)
        }
        sparse = SparseVector.from_mapping(weights)
        return Embedding(dense=dense, sparse=sparse, model_id=self._model_id)
