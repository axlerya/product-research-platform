"""Alembic env: онлайн-миграции через async-движок SQLAlchemy.

URL берётся из alembic-конфига (переопределяется в тестах) или из настроек
сервиса (RESEARCH_AGENT_DATABASE_URL). target_metadata — Base.metadata со
стабильной naming convention, поэтому автогенерация детерминирована.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from research_agent_service.infrastructure.config import get_settings
from research_agent_service.infrastructure.db import models  # noqa: F401
from research_agent_service.infrastructure.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    return (
        config.get_main_option("sqlalchemy.url") or get_settings().database_url
    )


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Генерация SQL без подключения к БД (alembic upgrade --sql)."""
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = async_engine_from_config(
        {"sqlalchemy.url": _url()}, prefix="sqlalchemy."
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    """Применение миграций через async-движок."""
    asyncio.run(_run_online())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
