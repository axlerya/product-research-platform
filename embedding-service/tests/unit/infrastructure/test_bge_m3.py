"""Unit-тесты BgeM3EmbeddingProvider на fake-энкодере (без torch/весов)."""

from typing import Any

import pytest

from embedding_service.application.exceptions import (
    InferenceError,
    ProbeFailed,
)
from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.infrastructure.embedding.bge_m3 import (
    BgeM3EmbeddingProvider,
)


def _mid(dim: int = 8) -> EmbeddingModelId:
    return EmbeddingModelId(
        name="BAAI/bge-m3",
        revision="unknown",
        pooling="cls",
        normalized=True,
        dim=dim,
    )


class _FakeEncoder:
    """Утиный тип BGEM3FlagModel: возвращает dense_vecs/lexical_weights."""

    def __init__(
        self,
        *,
        dim: int = 8,
        sparse_terms: int = 3,
        raise_exc: Exception | None = None,
        dense_dim: int | None = None,
    ) -> None:
        self._dim = dim
        self._sparse_terms = sparse_terms
        self._raise = raise_exc
        self._dense_dim = dense_dim
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def encode(self, sentences: list[str], **kwargs: Any) -> dict[str, Any]:
        self.calls.append((list(sentences), kwargs))
        if self._raise is not None:
            raise self._raise
        width = self._dense_dim or self._dim
        return {
            "dense_vecs": [
                [float(len(s)) + i for i in range(width)] for s in sentences
            ],
            "lexical_weights": [
                {str(1000 + j): 0.5 for j in range(self._sparse_terms)}
                for _ in sentences
            ],
        }


def _provider(encoder: _FakeEncoder, dim: int = 8) -> BgeM3EmbeddingProvider:
    return BgeM3EmbeddingProvider(
        encoder, model_id=_mid(dim), max_length=8192, batch_size=16
    )


async def test_embed_converts_and_preserves_order() -> None:
    encoder = _FakeEncoder(dim=8)
    provider = _provider(encoder)
    out = await provider.embed(
        [EmbeddingText("a"), EmbeddingText("bb")],
        kind=EmbeddingKind.DOCUMENT,
    )
    assert len(out) == 2
    assert out[0].dense.dimension == 8
    assert len(out[0].sparse.indices) == 3
    assert out[0].model_id == _mid(8)
    _, kwargs = encoder.calls[0]
    assert kwargs["return_dense"] is True
    assert kwargs["return_sparse"] is True
    assert kwargs["max_length"] == 8192
    assert kwargs["batch_size"] == 16


async def test_empty_input_skips_encoder() -> None:
    encoder = _FakeEncoder()
    out = await _provider(encoder).embed([], kind=EmbeddingKind.QUERY)
    assert out == []
    assert encoder.calls == []


async def test_encoder_exception_wrapped() -> None:
    provider = _provider(_FakeEncoder(raise_exc=RuntimeError("boom")))
    with pytest.raises(InferenceError):
        await provider.embed([EmbeddingText("x")], kind=EmbeddingKind.DOCUMENT)


async def test_warmup_ok() -> None:
    await _provider(_FakeEncoder(dim=8, sparse_terms=3)).warmup()


async def test_warmup_empty_sparse_fails() -> None:
    provider = _provider(_FakeEncoder(dim=8, sparse_terms=0))
    with pytest.raises(ProbeFailed):
        await provider.warmup()


async def test_warmup_wrong_dim_fails() -> None:
    provider = _provider(_FakeEncoder(dim=8, dense_dim=4), dim=8)
    with pytest.raises(ProbeFailed):
        await provider.warmup()


async def test_probe_reports_model_key() -> None:
    provider = _provider(_FakeEncoder())
    assert provider.model_id == _mid(8)
    status = await provider.probe()
    assert status.loaded
    assert status.model_key == _mid(8).key


async def test_embed_via_dedicated_executor() -> None:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as executor:
        provider = BgeM3EmbeddingProvider(
            _FakeEncoder(dim=8), model_id=_mid(8), executor=executor
        )
        out = await provider.embed(
            [EmbeddingText("a")], kind=EmbeddingKind.DOCUMENT
        )
    assert len(out) == 1
    assert out[0].dense.dimension == 8


class _OomOnBatch:
    """Энкодер, падающий OOM на батче > 1, но проходящий на одиночном."""

    def encode(self, sentences: list[str], **kwargs: Any) -> dict[str, Any]:
        if len(sentences) > 1:
            raise _OOM
        return {
            "dense_vecs": [[float(len(sentences[0])) + i for i in range(8)]],
            "lexical_weights": [{"5": 0.5}],
        }


class _OOM(Exception):
    """Имитация torch.cuda.OutOfMemoryError."""


async def test_embed_oom_split_through_provider() -> None:
    provider = BgeM3EmbeddingProvider(
        _OomOnBatch(), model_id=_mid(8), oom_types=(_OOM,)
    )
    out = await provider.embed(
        [EmbeddingText("a"), EmbeddingText("bb")],
        kind=EmbeddingKind.DOCUMENT,
    )
    assert len(out) == 2  # дробление пополам, порядок сохранён
