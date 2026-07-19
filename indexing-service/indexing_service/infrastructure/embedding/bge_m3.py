"""Адаптер ``BgeM3EmbeddingModel`` — реализация порта ``EmbeddingModel``.

Модель BGE-M3 инъектируется как ``encoder`` (утиный тип ``BGEM3FlagModel``),
поэтому конвертация тестируется без загрузки ~2.3ГБ весов. Блокирующий
``encode`` уносится в поток, чтобы не блокировать event loop.
"""

import asyncio
from collections.abc import Sequence
from typing import Any, Protocol

from indexing_service.application.exceptions import EmbeddingError
from indexing_service.domain.value_objects.dense_vector import DenseVector
from indexing_service.domain.value_objects.embedding import Embedding
from indexing_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from indexing_service.domain.value_objects.search_text import SearchText
from indexing_service.infrastructure.embedding.sparse import (
    lexical_weights_to_sparse,
)


class Bgem3Encoder(Protocol):
    """Утиный тип ``FlagEmbedding.BGEM3FlagModel``."""

    def encode(self, sentences: list[str], **kwargs: Any) -> dict[str, Any]:
        """Возвращает ``{"dense_vecs": ..., "lexical_weights": ...}``."""
        ...


class BgeM3EmbeddingModel:
    """Строит dense + sparse эмбеддинги через BGE-M3."""

    def __init__(
        self,
        encoder: Bgem3Encoder,
        *,
        model_id: EmbeddingModelId,
        max_length: int = 8192,
        batch_size: int = 16,
    ) -> None:
        self._encoder = encoder
        self._model_id = model_id
        self._max_length = max_length
        self._batch_size = batch_size

    @property
    def model_id(self) -> EmbeddingModelId:
        return self._model_id

    async def embed_documents(
        self, texts: Sequence[SearchText]
    ) -> list[Embedding]:
        raw = [text.value for text in texts]
        output = await asyncio.to_thread(self._encode, raw)
        dense = output["dense_vecs"]
        sparse = output["lexical_weights"]
        return [
            Embedding(
                dense=DenseVector(tuple(float(x) for x in dense[i])),
                sparse=lexical_weights_to_sparse(sparse[i]),
                model_id=self._model_id,
            )
            for i in range(len(raw))
        ]

    def _encode(self, raw: list[str]) -> dict[str, Any]:
        try:
            return self._encoder.encode(
                raw,
                return_dense=True,
                return_sparse=True,
                max_length=self._max_length,
                batch_size=self._batch_size,
            )
        except Exception as exc:
            raise EmbeddingError(str(exc)) from exc


def load_bge_m3(
    *,
    model: str = "BAAI/bge-m3",
    revision: str = "",
    device: str = "cpu",
    dim: int = 1024,
) -> BgeM3EmbeddingModel:  # pragma: no cover - тяжёлая проводка (e2e)
    """Загружает реальную BGE-M3 (тянет FlagEmbedding/torch, lazy-импорт)."""
    from FlagEmbedding import BGEM3FlagModel

    encoder = BGEM3FlagModel(
        model, use_fp16=device != "cpu", devices=device
    )
    model_id = EmbeddingModelId(
        name=model,
        revision=revision or "unknown",
        pooling="cls",
        normalized=True,
        dim=dim,
    )
    return BgeM3EmbeddingModel(encoder, model_id=model_id)
