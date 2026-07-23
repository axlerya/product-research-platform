"""Заглушка embedding-service для локального smoke (§12, шаг 7).

Слушает ``embedding.jobs`` и на каждую команду
``embedding.documents.requested.v1`` немедленно отвечает событием
``embedding.documents.generated.v1`` с детерминированными векторами. Нужна,
чтобы прогнать конвейер целиком без модели, GPU и соседнего сервиса.

Это инструмент разработчика, а не часть сервиса: в проде команды забирает
настоящий embedding-service.
"""

import hashlib
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from faststream import FastStream
from faststream.rabbit import (
    ExchangeType,
    RabbitBroker,
    RabbitExchange,
    RabbitQueue,
)

_JOBS = RabbitExchange(
    "embedding.jobs", type=ExchangeType.TOPIC, durable=True
)
_EVENTS = RabbitExchange(
    "embedding.events", type=ExchangeType.TOPIC, durable=True
)
_REQUESTED = "embedding.documents.requested.v1"
_GENERATED = "embedding.documents.generated.v1"
_DEFAULT_DSN = "amqp://guest:guest@localhost:5672/"

_DIM = int(os.environ.get("INDEXING_EMBEDDING_DIM", "8"))
_MODEL_VERSION = os.environ.get(
    "FAKE_MODEL_VERSION", f"fake@v1|dim={_DIM}"
)

broker = RabbitBroker(
    os.environ.get("INDEXING_RABBITMQ_DSN", _DEFAULT_DSN)
)
app = FastStream(broker)


def _dense(text: str) -> list[float]:
    """Детерминированный вектор из хэша текста (без модели)."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [digest[i % len(digest)] / 255.0 for i in range(_DIM)]


def _result_item(item: dict[str, Any]) -> dict[str, Any]:
    text = item.get("text", "")
    if not text.strip():
        return {
            "text_id": item["text_id"],
            "status": "error",
            "error": {"code": "EMPTY_TEXT", "message": "пустой текст"},
        }
    return {
        "text_id": item["text_id"],
        "status": "ok",
        "dense": _dense(text),
        "sparse": {"indices": [1, 2], "values": [0.5, 0.25]},
        "token_count": max(1, len(text.split())),
    }


_QUEUE = RabbitQueue(
    "fake-embedding.requested", durable=True, routing_key=_REQUESTED
)


@broker.subscriber(_QUEUE, _JOBS)
async def handle_command(envelope: dict[str, Any]) -> None:
    """Отвечает на команду событием с готовыми векторами."""
    data = envelope.get("data", {})
    request_id = data["request_id"]
    generated = {
        "event_id": str(uuid4()),
        "event_type": _GENERATED,
        "event_version": "1.0",
        "aggregate_type": "embedding_job",
        "aggregate_id": request_id,
        "occurred_at": datetime.now(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "producer": "embedding-service",
        "data": {
            "request_id": request_id,
            "model_version": _MODEL_VERSION,
            "dim": _DIM,
            "results": [_result_item(i) for i in data.get("items", [])],
        },
    }
    await broker.publish(
        generated, exchange=_EVENTS, routing_key=_GENERATED
    )
