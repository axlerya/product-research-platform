"""Тесты publisher команд на эмбеддинг.

Возврат несматченного сообщения проверяется на настоящем брокере
(``tests/integration/test_unroutable_publish.py``): это поведение канала, а
не нашего кода.
"""

from indexing_service.infrastructure.messaging.broker import (
    RabbitEmbeddingPublisher,
)


class _StubBroker:
    """Брокер, запоминающий аргументы публикации."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def publish(self, payload: object, **kwargs: object) -> None:
        self.calls.append({"payload": payload, **kwargs})


async def test_publishes_command_to_jobs_exchange():
    """Команда уходит в exchange embedding.jobs с ключом события."""
    broker = _StubBroker()

    await RabbitEmbeddingPublisher(broker).publish(
        {"event_type": "embedding.documents.requested.v1"},
        routing_key="embedding.documents.requested.v1",
        message_id="m1",
        headers={},
    )

    call = broker.calls[0]
    assert call["routing_key"] == "embedding.documents.requested.v1"
    assert call["exchange"].name == "embedding.jobs"
    assert call["message_id"] == "m1"
