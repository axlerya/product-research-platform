"""Контракт топологии RabbitMQ между тремя сервисами конвейера.

Exchange, очереди и routing keys объявляются кодом разных сервисов
независимо. Проверяем на живом брокере, что они действительно сошлись: иначе
сообщения молча уходят в никуда.
"""

from typing import Any

import httpx
import pytest

from tests.support.stand import Stand

pytestmark = pytest.mark.contract

_AUTH = ("guest", "guest")
_VHOST = "%2F"

_EXPECTED_EXCHANGES = {
    "catalog.events",
    "embedding.jobs",
    "embedding.events",
}
_EXPECTED_QUEUES = {
    "indexing.catalog.products",
    "embedding.documents.requests",
    "indexing.embeddings.generated",
}
# (exchange, очередь, routing key) — три стыка конвейера.
_EXPECTED_BINDINGS = {
    ("catalog.events", "indexing.catalog.products", "catalog.product.*"),
    (
        "embedding.jobs",
        "embedding.documents.requests",
        "embedding.documents.requested.v1",
    ),
    (
        "embedding.events",
        "indexing.embeddings.generated",
        "embedding.documents.generated.v1",
    ),
}


def _get(stand: Stand, path: str) -> Any:
    with httpx.Client(timeout=30.0, auth=_AUTH) as client:
        response = client.get(f"{stand.rabbit_management}/api/{path}")
        response.raise_for_status()
        return response.json()


def test_pipeline_exchanges_declared_as_durable_topics(stand: Stand) -> None:
    """Три обмена конвейера существуют, durable и типа topic."""
    exchanges = {
        item["name"]: item
        for item in _get(stand, f"exchanges/{_VHOST}")
        if item["name"] in _EXPECTED_EXCHANGES
    }

    assert set(exchanges) == _EXPECTED_EXCHANGES
    for item in exchanges.values():
        assert item["type"] == "topic"
        assert item["durable"] is True


def test_pipeline_queues_declared_and_durable(stand: Stand) -> None:
    """Основные очереди трёх консюмеров существуют и durable."""
    queues = {
        item["name"]: item
        for item in _get(stand, f"queues/{_VHOST}")
        if item["name"] in _EXPECTED_QUEUES
    }

    assert set(queues) == _EXPECTED_QUEUES
    for item in queues.values():
        assert item["durable"] is True


def test_pipeline_bindings_match_routing_keys(stand: Stand) -> None:
    """Routing keys продюсеров и консюмеров сошлись на всех трёх стыках."""
    bindings = {
        (item["source"], item["destination"], item["routing_key"])
        for item in _get(stand, f"bindings/{_VHOST}")
        if item["destination_type"] == "queue"
    }

    assert _EXPECTED_BINDINGS <= bindings


def test_embedding_requests_queue_is_quorum(stand: Stand) -> None:
    """Очередь команд эмбеддинга — quorum (требует брокер не ниже 3.13)."""
    queues = {item["name"]: item for item in _get(stand, f"queues/{_VHOST}")}

    assert queues["embedding.documents.requests"]["type"] == "quorum"
