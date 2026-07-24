"""Фикстуры интеграционных тестов: PostgreSQL в контейнере."""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.postgres import PostgresContainer

from research_agent_service.infrastructure.db import models  # noqa: F401
from research_agent_service.infrastructure.db.base import Base
from research_agent_service.infrastructure.db.engine import (
    build_engine,
    build_session_factory,
)


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Поднимает Postgres в контейнере, отдаёт asyncpg-URL."""
    with PostgresContainer("postgres:16-alpine") as container:
        url = container.get_connection_url()
        yield url.replace("+psycopg2", "+asyncpg")


@pytest.fixture(scope="session")
def rabbitmq_url() -> Iterator[str]:
    """Поднимает RabbitMQ в контейнере, отдаёт AMQP-URL.

    Ждём лог «Server startup complete» вместо flaky pika-пробы: async-клиент
    (aio-pika) подключается уже к готовому брокеру.
    """
    container = DockerContainer("rabbitmq:3.13").with_exposed_ports(5672)
    container.start()
    try:
        wait_for_logs(container, "Server startup complete", timeout=120)
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5672)
        yield f"amqp://guest:guest@{host}:{port}/"
    finally:
        container.stop()


@pytest_asyncio.fixture
async def session_factory(
    postgres_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Свежая схема на каждый тест (drop/create), фабрика сессий."""
    engine = build_engine(postgres_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield build_session_factory(engine)
    await engine.dispose()
