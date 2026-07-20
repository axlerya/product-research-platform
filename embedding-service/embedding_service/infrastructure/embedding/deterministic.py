"""``DeterministicEmbeddingProvider`` — FAKE-провайдер для CI/smoke.

Вектор выводится из sha256 текста, поэтому вывод стабилен и воспроизводим
(те же golden при перезапусках) — без загрузки модели, torch и GPU.
"""

import hashlib
import math
import random
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

_VOCAB_SIZE = 250_000


class DeterministicEmbeddingProvider:
    """Хэш → L2-нормированный dense + каноничный sparse. Без модели/torch."""

    def __init__(
        self, *, model_id: EmbeddingModelId, sparse_terms: int = 8
    ) -> None:
        self._model_id = model_id
        self._sparse_terms = sparse_terms

    @property
    def model_id(self) -> EmbeddingModelId:
        return self._model_id

    async def embed(
        self, texts: Sequence[EmbeddingText], *, kind: EmbeddingKind
    ) -> list[Embedding]:
        return [self._one(text.value) for text in texts]

    def _one(self, text: str) -> Embedding:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        rng = random.Random(int.from_bytes(digest, "big"))
        dense = DenseVector(
            self._l2_normalize(
                tuple(rng.uniform(-1.0, 1.0) for _ in range(self._model_id.dim))
            )
        )
        weights = {
            rng.randrange(_VOCAB_SIZE): rng.uniform(0.01, 1.0)
            for _ in range(self._sparse_terms)
        }
        return Embedding(
            dense=dense,
            sparse=SparseVector.from_mapping(weights),
            model_id=self._model_id,
        )

    @staticmethod
    def _l2_normalize(values: tuple[float, ...]) -> tuple[float, ...]:
        norm = math.sqrt(sum(v * v for v in values))
        if norm == 0.0:  # pragma: no cover - вырожденный случай (все нули)
            return values
        return tuple(v / norm for v in values)

    async def warmup(self) -> None:
        return None

    async def probe(self) -> ProviderStatus:
        return ProviderStatus(
            loaded=True,
            device="cpu",
            precision="fake",
            degraded=False,
            model_key=self._model_id.key,
        )
