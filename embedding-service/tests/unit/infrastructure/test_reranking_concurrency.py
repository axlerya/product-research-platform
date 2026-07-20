"""Unit-тесты ``ConcurrencyGuardedRerankerProvider``: чанки/таймаут/семафор."""

import asyncio
from collections.abc import Sequence

import pytest

from embedding_service.application.dto import ProviderStatus
from embedding_service.application.exceptions import InferenceTimeoutError
from embedding_service.domain.value_objects.reranking.reranker_model_id import (
    RerankerModelId,
)
from embedding_service.infrastructure.reranking.concurrency import (
    ConcurrencyGuardedRerankerProvider,
)

_MODEL_ID = RerankerModelId(
    name="BAAI/bge-reranker-v2-m3", revision="unknown", normalized=True
)
_STATUS = ProviderStatus(
    loaded=True,
    device="cpu",
    precision="fp32",
    degraded=False,
    model_key=_MODEL_ID.key,
)


class _RecordingInner:
    """Внутренний провайдер: считает пик параллелизма и видимые чанки."""

    def __init__(self, *, delay: float = 0.0) -> None:
        self.calls: list[list[str]] = []
        self.max_concurrent = 0
        self.warmed = False
        self.closed = False
        self._active = 0
        self._delay = delay

    @property
    def model_id(self) -> RerankerModelId:
        return _MODEL_ID

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        self._active += 1
        self.max_concurrent = max(self.max_concurrent, self._active)
        self.calls.append(list(documents))
        if self._delay:
            await asyncio.sleep(self._delay)
        self._active -= 1
        return [float(len(doc)) for doc in documents]

    async def warmup(self) -> None:
        self.warmed = True

    async def probe(self) -> ProviderStatus:
        return _STATUS

    async def aclose(self) -> None:
        self.closed = True


def _guard(
    inner: _RecordingInner, *, batch_size: int = 4, timeout_s: float = 5.0
) -> ConcurrencyGuardedRerankerProvider:
    return ConcurrencyGuardedRerankerProvider(
        inner,
        max_concurrent=1,
        batch_size=batch_size,
        timeout_s=timeout_s,
    )


class TestConcurrencyGuard:
    async def test_chunks_by_batch_size_preserving_order(self) -> None:
        inner = _RecordingInner()
        scores = await _guard(inner, batch_size=2).rerank(
            "q", ["a", "bb", "ccc", "dddd", "e"]
        )
        assert inner.calls == [["a", "bb"], ["ccc", "dddd"], ["e"]]
        assert scores == [1.0, 2.0, 3.0, 4.0, 1.0]

    async def test_timeout_raises_inference_timeout(self) -> None:
        inner = _RecordingInner(delay=0.2)
        guard = _guard(inner, batch_size=10, timeout_s=0.01)
        with pytest.raises(InferenceTimeoutError):
            await guard.rerank("q", ["a", "b"])

    async def test_semaphore_serializes_concurrent_calls(self) -> None:
        inner = _RecordingInner(delay=0.05)
        guard = _guard(inner, batch_size=10)
        await asyncio.gather(guard.rerank("q", ["a"]), guard.rerank("q", ["b"]))
        # max_concurrent=1 → внутренний провайдер не видит двух активных.
        assert inner.max_concurrent == 1

    async def test_empty_documents_returns_empty(self) -> None:
        assert await _guard(_RecordingInner()).rerank("q", []) == []

    async def test_delegates_warmup_probe_aclose(self) -> None:
        inner = _RecordingInner()
        guard = _guard(inner)
        await guard.warmup()
        status = await guard.probe()
        await guard.aclose()
        assert inner.warmed and inner.closed
        assert status.loaded is True
        assert guard.model_id.key == _MODEL_ID.key

    async def test_aclose_noop_when_inner_lacks_aclose(self) -> None:
        class _NoClose:
            @property
            def model_id(self) -> RerankerModelId:
                return _MODEL_ID

            async def rerank(
                self, query: str, documents: Sequence[str]
            ) -> list[float]:
                return [0.0 for _ in documents]

            async def warmup(self) -> None: ...

            async def probe(self) -> ProviderStatus:
                return _STATUS

        guard = ConcurrencyGuardedRerankerProvider(
            _NoClose(), max_concurrent=1, batch_size=4, timeout_s=5.0
        )
        # Внутренний без aclose — guard.aclose() безопасен (no-op).
        await guard.aclose()
