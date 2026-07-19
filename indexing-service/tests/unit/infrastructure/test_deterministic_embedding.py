"""Тесты детерминированного эмбеддера (FAKE-режим)."""

from indexing_service.domain.value_objects.search_text import SearchText
from indexing_service.infrastructure.embedding.deterministic import (
    DeterministicEmbeddingModel,
)


async def test_dim_matches_model():
    model = DeterministicEmbeddingModel(dim=8)
    [result] = await model.embed_documents([SearchText("товар")])
    assert result.dense.dimension == 8
    assert result.model_id.dim == 8


async def test_stable_across_calls():
    model = DeterministicEmbeddingModel(dim=8)
    [first] = await model.embed_documents([SearchText("x")])
    [second] = await model.embed_documents([SearchText("x")])
    assert first.dense.values == second.dense.values
    assert first.sparse.indices == second.sparse.indices


async def test_different_text_differs():
    model = DeterministicEmbeddingModel(dim=8)
    [left] = await model.embed_documents([SearchText("a")])
    [right] = await model.embed_documents([SearchText("b")])
    assert left.dense.values != right.dense.values
