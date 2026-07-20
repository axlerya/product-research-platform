"""Фикстуры integration-тестов (реальные Qdrant/RabbitMQ/Postgres)."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.qdrant import QdrantContainer

from alembic import command

_QDRANT_IMAGE = "qdrant/qdrant:v1.13.5"
_PG_IMAGE = "postgres:16-alpine"
_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def qdrant_container():
    with QdrantContainer(_QDRANT_IMAGE) as container:
        yield container


@pytest_asyncio.fixture
async def qdrant_client(qdrant_container):
    client = qdrant_container.get_async_client()
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture(scope="session")
def rabbitmq_url():
    from testcontainers.rabbitmq import RabbitMqContainer

    with RabbitMqContainer("rabbitmq:3.13-management-alpine") as rabbit:
        params = rabbit.get_connection_params()
        yield f"amqp://guest:guest@{params.host}:{params.port}/"


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """Поднимает Postgres и накатывает схему настоящими миграциями."""
    with PostgresContainer(_PG_IMAGE) as pg:
        url = pg.get_connection_url().replace("+psycopg2", "+asyncpg")
        cfg = Config(str(_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(_ROOT / "alembic"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        yield url


@pytest_asyncio.fixture
async def sessionmaker_(pg_url: str) -> AsyncIterator[async_sessionmaker]:
    """Чистая фабрика сессий: очищает таблицы перед каждым тестом."""
    engine = create_async_engine(pg_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE indexing_jobs, embedding_requests, outbox "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()
