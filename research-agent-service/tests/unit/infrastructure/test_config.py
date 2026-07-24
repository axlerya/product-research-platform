"""Тесты настроек сервиса."""

import pytest

from research_agent_service.infrastructure.config import Settings, get_settings


def test_defaults() -> None:
    """Значения по умолчанию заданы; трейсинг выключен."""
    settings = Settings()

    assert settings.service_name == "research-agent-service"
    assert settings.otlp_endpoint == ""


def test_catalog_base_url_points_at_service_http_port() -> None:
    """Каталог слушает 8000 — умолчание обязано вести туда же."""
    assert Settings().catalog_base_url == "http://localhost:8000"


def test_web_search_base_url_defaults_to_public_provider() -> None:
    """Пустой base_url = публичный эндпоинт провайдера (прежнее поведение)."""
    assert Settings().web_search_base_url == ""


def test_web_search_base_url_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Адрес web-поиска подменяется окружением (локальный провайдер)."""
    monkeypatch.setenv(
        "RESEARCH_AGENT_WEB_SEARCH_BASE_URL", "http://doubles:8000"
    )

    assert Settings().web_search_base_url == "http://doubles:8000"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Переменная окружения с префиксом переопределяет значение."""
    monkeypatch.setenv("RESEARCH_AGENT_LOG_LEVEL", "DEBUG")

    assert Settings().log_level == "DEBUG"


def test_get_settings_is_cached() -> None:
    """get_settings возвращает один и тот же экземпляр."""
    get_settings.cache_clear()

    assert get_settings() is get_settings()


def test_llm_settings_defaults() -> None:
    """LLM-настройки: кастомный base_url, thinking выключен по умолчанию."""
    llm = Settings().llm

    assert llm.base_url == "http://localhost:8001/v1"
    assert llm.enable_thinking is False


def test_llm_nested_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Вложенные переменные RESEARCH_AGENT_LLM__* переопределяют LLM."""
    monkeypatch.setenv("RESEARCH_AGENT_LLM__BASE_URL", "http://custom/v1")
    monkeypatch.setenv("RESEARCH_AGENT_LLM__MODEL", "gpt-x")

    settings = Settings()

    assert settings.llm.base_url == "http://custom/v1"
    assert settings.llm.model == "gpt-x"
