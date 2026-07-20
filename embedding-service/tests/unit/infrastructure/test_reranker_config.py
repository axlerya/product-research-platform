"""Unit-тесты ``RerankerSettings`` — изолированная конфигурация reranker."""

from embedding_service.infrastructure.reranker_config import (
    RerankerSettings,
    get_reranker_settings,
)


class TestRerankerSettings:
    def test_defaults_disabled(self) -> None:
        settings = RerankerSettings(_env_file=None)
        # По умолчанию reranker выключен — «прежний режим» сервиса.
        assert settings.enabled is False
        assert settings.provider_mode == "bge_reranker"
        assert settings.model == "BAAI/bge-reranker-v2-m3"

    def test_build_model_id(self) -> None:
        settings = RerankerSettings(_env_file=None, revision="")
        model_id = settings.build_model_id()
        assert model_id.name == "BAAI/bge-reranker-v2-m3"
        assert model_id.revision == "unknown"
        assert model_id.key.endswith("|norm=1")

    def test_limits(self) -> None:
        settings = RerankerSettings(
            _env_file=None, max_documents=10, max_query_chars=50
        )
        limits = settings.limits()
        assert limits.max_documents == 10
        assert limits.max_query_chars == 50

    def test_env_prefix_override(self, monkeypatch) -> None:
        monkeypatch.setenv("RERANKER_ENABLED", "true")
        monkeypatch.setenv("RERANKER_MAX_BATCH_SIZE", "64")
        settings = RerankerSettings(_env_file=None)
        assert settings.enabled is True
        assert settings.max_batch_size == 64


def test_get_reranker_settings_is_cached() -> None:
    assert get_reranker_settings() is get_reranker_settings()
