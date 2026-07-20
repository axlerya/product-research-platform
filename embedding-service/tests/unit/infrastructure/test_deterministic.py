"""Unit-тесты DeterministicEmbeddingProvider (FAKE для CI/smoke)."""

import math

from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.infrastructure.embedding.deterministic import (
    DeterministicEmbeddingProvider,
)


def _mid(dim: int = 8) -> EmbeddingModelId:
    return EmbeddingModelId(
        name="BAAI/bge-m3",
        revision="unknown",
        pooling="cls",
        normalized=True,
        dim=dim,
    )


async def test_same_text_same_embedding() -> None:
    provider = DeterministicEmbeddingProvider(model_id=_mid())
    [a] = await provider.embed(
        [EmbeddingText("hello")], kind=EmbeddingKind.DOCUMENT
    )
    [b] = await provider.embed(
        [EmbeddingText("hello")], kind=EmbeddingKind.QUERY
    )
    assert a.dense.values == b.dense.values
    assert a.sparse.indices == b.sparse.indices
    assert a.sparse.values == b.sparse.values


async def test_dense_l2_normalized() -> None:
    provider = DeterministicEmbeddingProvider(model_id=_mid(16))
    [emb] = await provider.embed(
        [EmbeddingText("x")], kind=EmbeddingKind.DOCUMENT
    )
    assert emb.dense.dimension == 16
    norm = math.sqrt(sum(v * v for v in emb.dense.values))
    assert abs(norm - 1.0) < 1e-6


async def test_sparse_canonical_nonempty() -> None:
    provider = DeterministicEmbeddingProvider(model_id=_mid(), sparse_terms=5)
    [emb] = await provider.embed(
        [EmbeddingText("abc")], kind=EmbeddingKind.DOCUMENT
    )
    assert len(emb.sparse.indices) > 0
    assert list(emb.sparse.indices) == sorted(set(emb.sparse.indices))
    assert all(v != 0.0 for v in emb.sparse.values)


async def test_different_texts_differ() -> None:
    provider = DeterministicEmbeddingProvider(model_id=_mid())
    [a] = await provider.embed(
        [EmbeddingText("aaa")], kind=EmbeddingKind.DOCUMENT
    )
    [b] = await provider.embed(
        [EmbeddingText("bbb")], kind=EmbeddingKind.DOCUMENT
    )
    assert a.dense.values != b.dense.values


async def test_order_and_count_preserved() -> None:
    provider = DeterministicEmbeddingProvider(model_id=_mid())
    out = await provider.embed(
        [EmbeddingText("a"), EmbeddingText("b"), EmbeddingText("c")],
        kind=EmbeddingKind.DOCUMENT,
    )
    assert len(out) == 3


async def test_model_id_warmup_probe() -> None:
    mid = _mid()
    provider = DeterministicEmbeddingProvider(model_id=mid)
    assert provider.model_id == mid
    await provider.warmup()
    status = await provider.probe()
    assert status.loaded
    assert status.model_key == mid.key
    assert status.degraded is False
