"""Unit-тесты BatchingEmbeddingProvider (полосы, коалессинг, backpressure)."""

import asyncio
from collections.abc import Sequence

import pytest

from embedding_service.application.exceptions import (
    InferenceError,
    InferenceOverloadedError,
    InferenceTimeoutError,
)
from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.infrastructure.embedding.batching_provider import (
    BatchingConfig,
    BatchingEmbeddingProvider,
)
from tests.support.fakes import FakeEmbeddingProvider


def _config(
    *,
    max_batch_size: int = 8,
    batch_wait_ms: int = 15,
    query_batch_wait_ms: int = 15,
    max_concurrent_inferences: int = 1,
    max_queue_size: int = 100,
    inference_timeout_s: float = 5.0,
) -> BatchingConfig:
    return BatchingConfig(
        max_batch_size=max_batch_size,
        batch_wait_ms=batch_wait_ms,
        query_batch_wait_ms=query_batch_wait_ms,
        max_concurrent_inferences=max_concurrent_inferences,
        max_queue_size=max_queue_size,
        inference_timeout_s=inference_timeout_s,
    )


class _BlockingInner:
    """Inner-провайдер, блокирующийся на embed до set() события."""

    def __init__(self, inner: FakeEmbeddingProvider) -> None:
        self._inner = inner
        self.gate = asyncio.Event()

    @property
    def model_id(self):
        return self._inner.model_id

    async def embed(
        self, texts: Sequence[EmbeddingText], *, kind: EmbeddingKind
    ) -> list[Embedding]:
        await self.gate.wait()
        return await self._inner.embed(texts, kind=kind)

    async def warmup(self) -> None:
        return None

    async def probe(self):
        return await self._inner.probe()


async def test_model_id_delegated() -> None:
    inner = FakeEmbeddingProvider(dim=4)
    provider = BatchingEmbeddingProvider(inner, _config())
    assert provider.model_id == inner.model_id
    await provider.aclose()


async def test_empty_input() -> None:
    provider = BatchingEmbeddingProvider(FakeEmbeddingProvider(), _config())
    assert await provider.embed([], kind=EmbeddingKind.QUERY) == []
    await provider.aclose()


async def test_single_batch_order_preserved() -> None:
    inner = FakeEmbeddingProvider(dim=4)
    provider = BatchingEmbeddingProvider(inner, _config())
    out = await provider.embed(
        [EmbeddingText("a"), EmbeddingText("bbbb"), EmbeddingText("cc")],
        kind=EmbeddingKind.DOCUMENT,
    )
    # dense[0] у FakeEmbeddingProvider == длина текста
    assert [e.dense.values[0] for e in out] == [1.0, 4.0, 2.0]
    await provider.aclose()


async def test_concurrent_calls_coalesce() -> None:
    inner = FakeEmbeddingProvider(dim=4)
    provider = BatchingEmbeddingProvider(inner, _config(max_batch_size=8))
    results = await asyncio.gather(
        provider.embed([EmbeddingText("a")], kind=EmbeddingKind.DOCUMENT),
        provider.embed([EmbeddingText("bbbb")], kind=EmbeddingKind.DOCUMENT),
        provider.embed([EmbeddingText("cc")], kind=EmbeddingKind.DOCUMENT),
    )
    # три вызова слились в один прогон инференса
    assert len(inner.embed_calls) == 1
    assert len(inner.embed_calls[0][0]) == 3
    # каждый вызов получил свой правильный вектор
    assert results[0][0].dense.values[0] == 1.0
    assert results[1][0].dense.values[0] == 4.0
    assert results[2][0].dense.values[0] == 2.0
    await provider.aclose()


async def test_backpressure_overloaded() -> None:
    inner = FakeEmbeddingProvider(dim=4)
    blocking = _BlockingInner(inner)
    provider = BatchingEmbeddingProvider(blocking, _config(max_queue_size=2))
    # первый батч занимает worker (inner блокируется) — глубина 2
    first = asyncio.create_task(
        provider.embed(
            [EmbeddingText("a"), EmbeddingText("b")],
            kind=EmbeddingKind.DOCUMENT,
        )
    )
    await asyncio.sleep(0.05)  # дать worker вынуть батч и застрять в inner
    with pytest.raises(InferenceOverloadedError):
        await provider.embed([EmbeddingText("c")], kind=EmbeddingKind.QUERY)
    blocking.gate.set()
    await first
    await provider.aclose()


async def test_inference_timeout() -> None:
    inner = FakeEmbeddingProvider(dim=4)
    blocking = _BlockingInner(inner)  # gate никогда не set → зависание
    provider = BatchingEmbeddingProvider(
        blocking, _config(inference_timeout_s=0.05)
    )
    with pytest.raises(InferenceTimeoutError):
        await provider.embed([EmbeddingText("a")], kind=EmbeddingKind.DOCUMENT)
    await provider.aclose()


async def test_inner_error_propagates() -> None:
    inner = FakeEmbeddingProvider(embed_error=InferenceError("boom"))
    provider = BatchingEmbeddingProvider(inner, _config())
    with pytest.raises(InferenceError):
        await provider.embed([EmbeddingText("a")], kind=EmbeddingKind.DOCUMENT)
    await provider.aclose()


async def test_generic_inner_error_wrapped() -> None:
    inner = FakeEmbeddingProvider(embed_error=RuntimeError("weird"))
    provider = BatchingEmbeddingProvider(inner, _config())
    with pytest.raises(InferenceError):
        await provider.embed([EmbeddingText("a")], kind=EmbeddingKind.DOCUMENT)
    await provider.aclose()


async def test_query_lane_priority() -> None:
    # белый ящик: при обеих непустых полосах worker берёт QUERY первой
    inner = FakeEmbeddingProvider(dim=4)
    provider = BatchingEmbeddingProvider(inner, _config())
    provider._enqueue([EmbeddingText("doc")], EmbeddingKind.DOCUMENT)
    provider._enqueue([EmbeddingText("qry")], EmbeddingKind.QUERY)
    batch, kind = provider._collect()
    assert kind is EmbeddingKind.QUERY
    assert batch[0].text.value == "qry"


async def test_collect_empty_returns_document_default() -> None:
    provider = BatchingEmbeddingProvider(FakeEmbeddingProvider(), _config())
    batch, kind = provider._collect()
    assert batch == []
    assert kind is EmbeddingKind.DOCUMENT
    await provider.aclose()


async def test_warmup_and_probe_delegate() -> None:
    inner = FakeEmbeddingProvider(dim=4)
    provider = BatchingEmbeddingProvider(inner, _config())
    await provider.warmup()
    status = await provider.probe()
    assert status.model_key == inner.model_id.key
    await provider.aclose()


async def test_query_lane_embed_through_worker() -> None:
    provider = BatchingEmbeddingProvider(
        FakeEmbeddingProvider(dim=4), _config()
    )
    out = await provider.embed([EmbeddingText("q")], kind=EmbeddingKind.QUERY)
    assert len(out) == 1
    await provider.aclose()


async def test_cancelled_awaiter_skipped_on_success() -> None:
    blocking = _BlockingInner(FakeEmbeddingProvider(dim=4))
    provider = BatchingEmbeddingProvider(
        blocking, _config(batch_wait_ms=5, query_batch_wait_ms=5)
    )
    task = asyncio.create_task(
        provider.embed([EmbeddingText("a")], kind=EmbeddingKind.DOCUMENT)
    )
    await asyncio.sleep(0.03)  # worker застрял в inner
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    blocking.gate.set()  # inner отдаёт результат → future уже отменён → skip
    await asyncio.sleep(0.03)
    await provider.aclose()


async def test_cancelled_awaiter_skipped_on_timeout() -> None:
    blocking = _BlockingInner(FakeEmbeddingProvider(dim=4))  # gate не set
    provider = BatchingEmbeddingProvider(
        blocking,
        _config(
            inference_timeout_s=0.08, batch_wait_ms=5, query_batch_wait_ms=5
        ),
    )
    task = asyncio.create_task(
        provider.embed([EmbeddingText("a")], kind=EmbeddingKind.DOCUMENT)
    )
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.12)  # инференс таймаутит → _fail на отменённом → skip
    await provider.aclose()
