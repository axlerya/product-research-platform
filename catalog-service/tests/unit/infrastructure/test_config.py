"""Тесты настроек сервиса (``Settings``)."""

from catalog_service.infrastructure.config import Settings, get_settings


def test_get_settings_returns_settings_instance():
    assert isinstance(get_settings(), Settings)


def test_defaults():
    settings = Settings()
    assert settings.default_currency == "RUB"
    assert settings.outbox_batch_size == 100
    assert "asyncpg" in settings.database_url


def test_env_override(monkeypatch):
    monkeypatch.setenv("CATALOG_DEFAULT_CURRENCY", "USD")
    monkeypatch.setenv("CATALOG_OUTBOX_BATCH_SIZE", "50")
    settings = Settings()
    assert settings.default_currency == "USD"
    assert settings.outbox_batch_size == 50
