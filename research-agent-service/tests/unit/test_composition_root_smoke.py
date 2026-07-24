"""Дымовые тесты composition root: сборка без сетевых подключений.

Модули bootstrap/main/relay вне покрытия, но их проводка должна собираться
без ошибок импорта/сигнатур. Клиенты создаются лениво (без коннекта).
"""

from fastapi import FastAPI

from research_agent_service.infrastructure.config import Settings


async def test_container_builds_and_closes() -> None:
    """Контейнер собирает все use cases и закрывается без коннектов."""
    from research_agent_service.bootstrap import build_container

    container = build_container(Settings())
    services = container.api_services

    assert services.answer_query is not None
    assert services.submit_feedback is not None
    assert services.list_queries is not None
    assert services.get_query is not None

    await container.aclose()


def test_build_app_returns_fastapi() -> None:
    """main.build_app даёт FastAPI-приложение."""
    from research_agent_service.main import build_app

    assert isinstance(build_app(), FastAPI)


def test_build_relay_app() -> None:
    """relay_app.build_relay_app собирается из настроек."""
    from research_agent_service.presentation.messaging.relay_app import (
        build_relay_app,
    )

    assert build_relay_app(Settings()) is not None
