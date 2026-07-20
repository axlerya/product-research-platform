"""Unit-тест фабрики провайдера (deterministic-режим)."""

import pytest

from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.infrastructure.config import Settings
from embedding_service.infrastructure.embedding import factory
from embedding_service.infrastructure.embedding.batching_provider import (
    BatchingEmbeddingProvider,
)
from embedding_service.infrastructure.embedding.deterministic import (
    DeterministicEmbeddingProvider,
)
from embedding_service.infrastructure.embedding.factory import build_provider


async def test_build_deterministic_provider() -> None:
    settings = Settings(_env_file=None, provider_mode="deterministic", dim=8)
    provider = build_provider(settings)
    assert isinstance(provider, BatchingEmbeddingProvider)
    assert provider.model_id.dim == 8
    out = await provider.embed([EmbeddingText("hi")], kind=EmbeddingKind.QUERY)
    assert len(out) == 1
    await provider.aclose()


def test_build_bge_mode_delegates_to_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None, provider_mode="bge_m3", dim=8)
    sentinel = DeterministicEmbeddingProvider(
        model_id=settings.build_model_id()
    )
    monkeypatch.setattr(factory, "_load_bge", lambda _settings: sentinel)
    provider = build_provider(settings)
    assert provider._inner is sentinel
