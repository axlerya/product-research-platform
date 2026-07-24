"""CLI: запуск API, relay и миграций (вне покрытия)."""

import argparse
import asyncio

import uvicorn
from alembic.config import Config

from alembic import command
from research_agent_service.infrastructure.config import get_settings
from research_agent_service.presentation.messaging.relay_app import (
    build_relay_app,
)

# Контейнерный сервис слушает все интерфейсы.
_HOST = "0.0.0.0"
_PORT = 8000


def _serve() -> None:
    uvicorn.run("research_agent_service.main:app", host=_HOST, port=_PORT)


def _relay() -> None:
    asyncio.run(build_relay_app(get_settings()).run())


def _migrate() -> None:
    command.upgrade(Config("alembic.ini"), "head")


_COMMANDS = {"serve": _serve, "relay": _relay, "migrate": _migrate}


def main(argv: list[str] | None = None) -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(prog="research-agent-service")
    parser.add_argument("command", choices=sorted(_COMMANDS))
    args = parser.parse_args(argv)
    _COMMANDS[args.command]()
