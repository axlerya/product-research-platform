"""Тест-фейки application-слоя — детерминированные, без I/O."""

from collections.abc import Sequence

from embedding_service.application.dto import ProviderStatus
from embedding_service.domain.value_objects.dense_vector import DenseVector
from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.domain.value_objects.sparse_vector import SparseVector
from embedding_service.domain.value_objects.token_count import TokenCount


def default_model_id(dim: int = 2) -> EmbeddingModelId:
    return EmbeddingModelId(
        name="BAAI/bge-m3",
        revision="unknown",
        pooling="cls",
        normalized=True,
        dim=dim,
    )


class FakeEmbeddingProvider:
    """Детерминированный провайдер: dense из длины текста, sparse фиксирован."""

    def __init__(
        self,
        *,
        dim: int = 2,
        embed_error: Exception | None = None,
        warmup_error: Exception | None = None,
        degraded: bool = False,
    ) -> None:
        self._model_id = default_model_id(dim)
        self._embed_error = embed_error
        self._warmup_error = warmup_error
        self._degraded = degraded
        self.embed_calls: list[tuple[list[str], EmbeddingKind]] = []
        self.warmup_calls = 0

    @property
    def model_id(self) -> EmbeddingModelId:
        return self._model_id

    async def embed(
        self, texts: Sequence[EmbeddingText], *, kind: EmbeddingKind
    ) -> list[Embedding]:
        self.embed_calls.append(([t.value for t in texts], kind))
        if self._embed_error is not None:
            raise self._embed_error
        return [self._one(text) for text in texts]

    def _one(self, text: EmbeddingText) -> Embedding:
        base = float(len(text.value))
        dense = DenseVector(tuple(base + i for i in range(self._model_id.dim)))
        return Embedding(
            dense=dense,
            sparse=SparseVector((1,), (0.5,)),
            model_id=self._model_id,
        )

    async def warmup(self) -> None:
        self.warmup_calls += 1
        if self._warmup_error is not None:
            raise self._warmup_error

    async def probe(self) -> ProviderStatus:
        return ProviderStatus(
            loaded=True,
            device="cpu",
            precision="fp32",
            degraded=self._degraded,
            model_key=self._model_id.key,
        )


class FakeTokenizer:
    """Токенайзер-фейк: счётчик из карты ``text -> count`` или дефолт."""

    def __init__(
        self, *, counts: dict[str, int] | None = None, default: int = 1
    ) -> None:
        self._counts = counts or {}
        self._default = default

    def count_tokens(self, text: EmbeddingText) -> TokenCount:
        return TokenCount(self._counts.get(text.value, self._default))

    def truncate(
        self, text: EmbeddingText, max_tokens: int
    ) -> tuple[EmbeddingText, TokenCount, bool]:
        return text, self.count_tokens(text), False
