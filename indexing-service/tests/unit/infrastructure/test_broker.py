"""Тесты publisher команд на эмбеддинг (подтверждение публикации)."""

import pytest
from pamqp.commands import Basic

from indexing_service.infrastructure.messaging.broker import (
    RabbitEmbeddingPublisher,
    UnroutableMessage,
)


class _StubBroker:
    """Брокер, возвращающий заданное подтверждение публикации."""

    def __init__(self, confirmation: object) -> None:
        self._confirmation = confirmation
        self.calls: list[dict] = []

    async def publish(self, payload: object, **kwargs: object) -> object:
        self.calls.append({"payload": payload, **kwargs})
        return self._confirmation


class _Confirmation:
    """Ответ брокера на публикацию (``delivery`` — Ack либо Return)."""

    def __init__(self, delivery: object) -> None:
        self.delivery = delivery


async def _publish(confirmation: object) -> _StubBroker:
    broker = _StubBroker(confirmation)
    await RabbitEmbeddingPublisher(broker).publish(
        {"event_type": "embedding.documents.requested.v1"},
        routing_key="embedding.documents.requested.v1",
        message_id="m1",
        headers={},
    )
    return broker


async def test_publishes_command_to_jobs_exchange():
    """Команда уходит в exchange embedding.jobs с ключом события."""
    broker = await _publish(_Confirmation(Basic.Ack()))

    assert broker.calls[0]["routing_key"] == (
        "embedding.documents.requested.v1"
    )
    assert broker.calls[0]["exchange"].name == "embedding.jobs"


async def test_returned_command_is_reported_as_failure():
    """Возврат брокером = недоставка: relay обязан повторить, а не забыть.

    Publish с mandatory сам не бросает — он отдаёт подтверждение с
    ``Basic.Return`` внутри. Без явной проверки outbox пометил бы такую
    команду опубликованной, и задание на эмбеддинг зависло бы до сверки.
    """
    with pytest.raises(UnroutableMessage) as failure:
        await _publish(_Confirmation(Basic.Return()))

    assert "embedding.documents.requested.v1" in str(failure.value)


async def test_missing_confirmation_is_reported_as_success():
    """Отсутствие подтверждения (канал без confirms) не ломает публикацию."""
    await _publish(None)
