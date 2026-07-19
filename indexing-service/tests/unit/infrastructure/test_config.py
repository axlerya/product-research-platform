"""Тесты настроек ``Settings`` (pydantic-settings, префикс INDEXING_)."""

from indexing_service.infrastructure.config import (
    EmbeddingMode,
    Settings,
    SourceMode,
)


def test_defaults():
    settings = Settings(_env_file=None)
    assert settings.collection_alias == "products"
    assert settings.default_currency == "RUB"
    assert settings.embedding_mode is EmbeddingMode.LOCAL
    assert settings.source_mode is SourceMode.HYBRID
    assert settings.embedding_dim == 1024
    assert settings.max_attempts == 5


def test_env_prefix_override(monkeypatch):
    monkeypatch.setenv("INDEXING_QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("INDEXING_PREFETCH_COUNT", "64")
    settings = Settings(_env_file=None)
    assert settings.qdrant_url == "http://qdrant:6333"
    assert settings.prefetch_count == 64


def test_enum_coercion_from_env(monkeypatch):
    monkeypatch.setenv("INDEXING_EMBEDDING_MODE", "fake")
    monkeypatch.setenv("INDEXING_SOURCE_MODE", "event")
    settings = Settings(_env_file=None)
    assert settings.embedding_mode is EmbeddingMode.FAKE
    assert settings.source_mode is SourceMode.EVENT
