"""Unit-тесты Settings (pydantic-settings, префикс EMBEDDING_)."""

import pytest

from embedding_service.infrastructure.config import Settings, get_settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.provider_mode == "bge_m3"
    assert settings.dim == 1024
    assert settings.grpc_port == 50051
    assert settings.device == "auto"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_GRPC_PORT", "9999")
    monkeypatch.setenv("EMBEDDING_PROVIDER_MODE", "deterministic")
    monkeypatch.setenv("EMBEDDING_DEVICE", "cpu")
    settings = Settings(_env_file=None)
    assert settings.grpc_port == 9999
    assert settings.provider_mode == "deterministic"
    assert settings.device == "cpu"


def test_build_model_id() -> None:
    mid = Settings(_env_file=None).build_model_id()
    assert mid.name == "BAAI/bge-m3"
    assert mid.dim == 1024
    assert mid.revision == "unknown"
    assert mid.key.endswith("|pool=cls|norm=1|dim=1024")


def test_build_model_id_uses_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_REVISION", "abc123")
    assert Settings(_env_file=None).build_model_id().revision == "abc123"


def test_limits_helpers() -> None:
    settings = Settings(_env_file=None)
    assert settings.document_limits().max_texts == 256
    assert settings.query_limits().max_texts == 32
    assert settings.document_limits().max_total_bytes == 4_194_304


def test_invalid_provider_mode_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER_MODE", "bogus")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_get_settings_is_cached_singleton() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
    assert isinstance(first, Settings)
