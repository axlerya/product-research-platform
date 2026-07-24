"""Тесты настроек сервиса."""

import pytest

from research_agent_service.infrastructure.config import Settings, get_settings


def test_defaults() -> None:
    """Значения по умолчанию заданы; трейсинг выключен."""
    settings = Settings()

    assert settings.service_name == "research-agent-service"
    assert settings.otlp_endpoint == ""


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Переменная окружения с префиксом переопределяет значение."""
    monkeypatch.setenv("RESEARCH_AGENT_LOG_LEVEL", "DEBUG")

    assert Settings().log_level == "DEBUG"


def test_get_settings_is_cached() -> None:
    """get_settings возвращает один и тот же экземпляр."""
    get_settings.cache_clear()

    assert get_settings() is get_settings()
