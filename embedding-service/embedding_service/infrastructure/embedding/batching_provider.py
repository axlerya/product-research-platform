"""``BatchingEmbeddingProvider`` — динамический micro-batcher за портом.

Декоратор ``EmbeddingProvider``: коалессит конкурентные вызовы ``embed`` в
общий прогон инференса, ограничивает параллелизм (``Semaphore``), даёт
backpressure ограниченной очередью и рассеивает результаты строго по порядку
входа. Две полосы: ``QUERY`` (приоритет) и ``DOCUMENT`` (throughput).
"""

import asyncio
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from embedding_service.application.dto import ProviderStatus
from embedding_service.application.exceptions import (
    ApplicationError,
    InferenceError,
    InferenceOverloadedError,
    InferenceTimeoutError,
)
from embedding_service.application.ports.embedding_provider import (
    EmbeddingProvider,
)
from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.embedding_text import EmbeddingText


@dataclass(frozen=True, slots=True)
class BatchingConfig:
    """Параметры батчинга и конкурентности."""

    max_batch_size: int
    batch_wait_ms: int
    query_batch_wait_ms: int
    max_concurrent_inferences: int
    max_queue_size: int
    inference_timeout_s: float


@dataclass(slots=True)
class _Waiter:
    text: EmbeddingText
    future: asyncio.Future[Embedding]


class BatchingEmbeddingProvider:
    """Оркестрация инференса поверх подлежащего провайдера."""

    def __init__(
        self, inner: EmbeddingProvider, config: BatchingConfig
    ) -> None:
        self._inner = inner
        self._cfg = config
        self._lanes: dict[EmbeddingKind, deque[_Waiter]] = {
            EmbeddingKind.QUERY: deque(),
            EmbeddingKind.DOCUMENT: deque(),
        }
        self._depth = 0
        self._sem = asyncio.Semaphore(config.max_concurrent_inferences)
        self._wake = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def model_id(self) -> EmbeddingModelId:
        return self._inner.model_id

    async def embed(
        self, texts: Sequence[EmbeddingText], *, kind: EmbeddingKind
    ) -> list[Embedding]:
        if not texts:
            return []
        if self._depth + len(texts) > self._cfg.max_queue_size:
            raise InferenceOverloadedError(queue_depth=self._depth)
        self._ensure_worker()
        waiters = self._enqueue(texts, kind)
        return list(await asyncio.gather(*(w.future for w in waiters)))

    async def warmup(self) -> None:
        await self._inner.warmup()

    async def probe(self) -> ProviderStatus:
        return await self._inner.probe()

    async def aclose(self) -> None:
        """Останавливает worker, дренируя оставшиеся батчи."""
        self._closed = True
        self._wake.set()
        if self._worker is not None:
            await self._worker
            self._worker = None

    # --- внутреннее ---

    def _ensure_worker(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run_worker())

    def _enqueue(
        self, texts: Sequence[EmbeddingText], kind: EmbeddingKind
    ) -> list[_Waiter]:
        loop = asyncio.get_running_loop()
        waiters = [_Waiter(text, loop.create_future()) for text in texts]
        self._lanes[kind].extend(waiters)
        self._depth += len(waiters)
        self._wake.set()
        return waiters

    def _has_pending(self) -> bool:
        return bool(
            self._lanes[EmbeddingKind.QUERY]
            or self._lanes[EmbeddingKind.DOCUMENT]
        )

    def _wait_seconds(self) -> float:
        if self._lanes[EmbeddingKind.QUERY]:
            return self._cfg.query_batch_wait_ms / 1000
        return self._cfg.batch_wait_ms / 1000

    def _collect(self) -> tuple[list[_Waiter], EmbeddingKind]:
        for kind in (EmbeddingKind.QUERY, EmbeddingKind.DOCUMENT):
            lane = self._lanes[kind]
            if lane:
                size = min(len(lane), self._cfg.max_batch_size)
                batch = [lane.popleft() for _ in range(size)]
                return batch, kind
        return [], EmbeddingKind.DOCUMENT

    async def _run_worker(self) -> None:
        while True:
            self._wake.clear()
            if not self._has_pending():
                if self._closed:
                    return
                await self._wake.wait()
                continue
            # окно накопления — коалессинг конкурентных вызовов
            await asyncio.sleep(self._wait_seconds())
            batch, kind = self._collect()
            async with self._sem:
                await self._infer_and_scatter(batch, kind)

    async def _infer_and_scatter(
        self, batch: list[_Waiter], kind: EmbeddingKind
    ) -> None:
        texts = [waiter.text for waiter in batch]
        try:
            embeddings = await asyncio.wait_for(
                self._inner.embed(texts, kind=kind),
                timeout=self._cfg.inference_timeout_s,
            )
        except TimeoutError:
            self._depth -= len(batch)
            self._fail(batch, InferenceTimeoutError())
            return
        except Exception as exc:
            self._depth -= len(batch)
            self._fail(batch, _as_transient(exc))
            return
        self._depth -= len(batch)
        for waiter, embedding in zip(batch, embeddings, strict=True):
            if not waiter.future.done():
                waiter.future.set_result(embedding)

    @staticmethod
    def _fail(batch: list[_Waiter], exc: ApplicationError) -> None:
        for waiter in batch:
            if not waiter.future.done():
                waiter.future.set_exception(exc)


def _as_transient(exc: Exception) -> ApplicationError:
    if isinstance(exc, ApplicationError):
        return exc
    return InferenceError(str(exc))
