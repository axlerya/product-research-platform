"""Тесты топологии RabbitMQ консюмера (§7.3)."""

from indexing_service.presentation.messaging.topology import (
    CATALOG_EXCHANGE,
    main_queue,
    parking_queue,
    retry_queue,
)


def test_main_queue_deadletters_to_retry():
    queue = main_queue()
    assert queue.arguments["x-dead-letter-exchange"] == "indexing.retry"
    assert queue.routing_key == "catalog.product.*"


def test_retry_queue_ttl_and_deadletter():
    queue = retry_queue(30000)
    assert queue.arguments["x-message-ttl"] == 30000
    assert queue.arguments["x-dead-letter-exchange"] == "indexing.requeue"


def test_parking_queue_has_no_ttl():
    assert "x-message-ttl" not in parking_queue().arguments


def test_catalog_exchange_is_topic_durable():
    assert CATALOG_EXCHANGE.name == "catalog.events"
