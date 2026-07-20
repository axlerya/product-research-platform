"""Smoke-тест каркаса: пакет и слои импортируются, версия объявлена."""

import embedding_service
from embedding_service import (
    application,
    domain,
    infrastructure,
    presentation,
)


def test_package_version() -> None:
    assert embedding_service.__version__ == "0.1.0"


def test_layers_importable() -> None:
    # Все четыре слоя Clean Architecture существуют как пакеты.
    for layer in (domain, application, infrastructure, presentation):
        assert layer.__name__.startswith("embedding_service.")
