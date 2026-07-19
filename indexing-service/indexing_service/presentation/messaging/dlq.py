"""Переотправка запаркованных (DLQ) сообщений в основной exchange (§7.3).

Дренирует parking-очередь и публикует каждое сообщение обратно в
``catalog.events`` с исходным routing key — для повторной обработки после
исправления причины. Идемпотентность консюмера (§6) делает replay
безопасным.
"""

from faststream.rabbit import RabbitBroker

from indexing_service.presentation.messaging.topology import (
    CATALOG_EXCHANGE,
    parking_queue,
)


async def replay_parked(broker: RabbitBroker, *, limit: int = 10000) -> int:
    """Переотправляет до ``limit`` сообщений из parking-DLQ (вернёт число)."""
    parking = await broker.declare_queue(parking_queue())
    replayed = 0
    while replayed < limit:
        message = await parking.get(no_ack=False, fail=False)
        if message is None:
            break
        async with message.process():
            await broker.publish(
                message.body,
                exchange=CATALOG_EXCHANGE,
                routing_key=message.routing_key,
                headers=dict(message.headers),
                persist=True,
            )
        replayed += 1
    return replayed
