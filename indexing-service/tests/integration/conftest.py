"""Фикстуры integration-тестов (реальные Qdrant/RabbitMQ, testcontainers)."""

import pytest
import pytest_asyncio
from testcontainers.qdrant import QdrantContainer

_QDRANT_IMAGE = "qdrant/qdrant:v1.13.5"


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
