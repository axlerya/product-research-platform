"""Тесты адаптера ``BgeM3EmbeddingModel`` на фейковом энкодере (без весов)."""

import pytest

from indexing_service.application.exceptions import EmbeddingError
from indexing_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from indexing_service.domain.value_objects.search_text import SearchText
from indexing_service.infrastructure.embedding.bge_m3 import (
    BgeM3EmbeddingModel,
)

_MODEL = EmbeddingModelId("BAAI/bge-m3", "rev", "cls", normalized=True, dim=4)


class _FakeEncoder:
    def __init__(self) -> None:
        self.kwargs: dict | None = None

    def encode(self, sentences, **kwargs):
        self.kwargs = kwargs
        count = len(sentences)
        return {
            "dense_vecs": [[0.1, 0.2, 0.3, 0.4] for _ in range(count)],
            "lexical_weights": [{"7": 0.5, "3": 0.2} for _ in range(count)],
        }


async def test_embed_documents_builds_embeddings():
    encoder = _FakeEncoder()
    model = BgeM3EmbeddingModel(encoder, model_id=_MODEL)
    result = await model.embed_documents([SearchText("a"), SearchText("b")])
    assert len(result) == 2
    assert result[0].dense.dimension == 4
    assert result[0].sparse.indices == (3, 7)
    assert result[0].model_id is _MODEL
    assert encoder.kwargs["return_dense"] is True
    assert encoder.kwargs["return_sparse"] is True


async def test_model_id_property():
    model = BgeM3EmbeddingModel(_FakeEncoder(), model_id=_MODEL)
    assert model.model_id is _MODEL


async def test_encode_failure_raises_embedding_error():
    class Boom:
        def encode(self, sentences, **kwargs):
            raise RuntimeError("oom")

    model = BgeM3EmbeddingModel(Boom(), model_id=_MODEL)
    with pytest.raises(EmbeddingError):
        await model.embed_documents([SearchText("a")])
