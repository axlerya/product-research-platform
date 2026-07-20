"""``ConcurrencyGuardedRerankerProvider`` — конкурентность/чанкинг/таймаут.

Обёртка над провайдером reranker: ограничивает число одновременных инференсов
(семафор), дробит документы на чанки по ``batch_size`` (порядок сохранён),
навешивает пер-чанк таймаут. Для запросного (sync) reranking одна полоса —
проще двухполосного документного батчера эмбеддингов.
"""

import asyncio
from collections.abc import Sequence

from embedding_service.application.dto import ProviderStatus
from embedding_service.application.exceptions import InferenceTimeoutError
from embedding_service.application.ports.reranker_provider import (
    RerankerProvider,
)
from embedding_service.domain.value_objects.reranking.reranker_model_id import (
    RerankerModelId,
)


class ConcurrencyGuardedRerankerProvider:
    """Ограничивает параллелизм и размер чанка reranker-инференса."""

    def __init__(
        self,
        inner: RerankerProvider,
        *,
        max_concurrent: int,
        batch_size: int,
        timeout_s: float,
    ) -> None:
        self._inner = inner
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._batch_size = batch_size
        self._timeout_s = timeout_s

    @property
    def model_id(self) -> RerankerModelId:
        return self._inner.model_id

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        docs = list(documents)
        scores: list[float] = []
        for start in range(0, len(docs), self._batch_size):
            chunk = docs[start : start + self._batch_size]
            scores.extend(await self._rerank_chunk(query, chunk))
        return scores

    async def _rerank_chunk(self, query: str, chunk: list[str]) -> list[float]:
        async with self._semaphore:
            try:
                return await asyncio.wait_for(
                    self._inner.rerank(query, chunk),
                    timeout=self._timeout_s,
                )
            except TimeoutError as exc:
                raise InferenceTimeoutError(
                    f"reranker: превышен таймаут {self._timeout_s}s"
                ) from exc

    async def warmup(self) -> None:
        await self._inner.warmup()

    async def probe(self) -> ProviderStatus:
        return await self._inner.probe()

    async def aclose(self) -> None:
        close = getattr(self._inner, "aclose", None)
        if close is not None:
            await close()
