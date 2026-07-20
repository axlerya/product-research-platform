"""``DeterministicRerankerProvider`` — FAKE-провайдер reranker для CI/smoke.

Скор выводится из sha256 пары ``(query, doc)``: стабилен и воспроизводим, без
загрузки модели, torch и GPU. Разные документы/запросы дают разные скоры —
достаточно для проверки порядка и top_n в тестах.
"""

import hashlib
from collections.abc import Sequence

from embedding_service.application.dto import ProviderStatus
from embedding_service.domain.value_objects.reranking.reranker_model_id import (
    RerankerModelId,
)


class DeterministicRerankerProvider:
    """Хэш пары (query, doc) → скор в ``[0, 1)``. Без модели/torch."""

    def __init__(self, *, model_id: RerankerModelId) -> None:
        self._model_id = model_id

    @property
    def model_id(self) -> RerankerModelId:
        return self._model_id

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        return [self._score(query, doc) for doc in documents]

    @staticmethod
    def _score(query: str, doc: str) -> float:
        digest = hashlib.sha256(f"{query}\x00{doc}".encode()).digest()
        return int.from_bytes(digest[:8], "big") / 2**64

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

    async def aclose(self) -> None:
        return None
