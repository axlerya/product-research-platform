"""Сборка команды ``embedding.documents.requested.v1`` → ``OutboxMessage``.

Прикладной слой: чистое преобразование ``EmbeddingRequest`` в self-contained
конверт команды (JSON-совместимый), который relay опубликует в exchange
``embedding.jobs`` как есть. Контракт принадлежит embedding-service — мы
tolerant producer и обязаны удовлетворять их consumer-схеме
(``contracts/embedding/producer/documents_requested.schema.json``).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from indexing_service.application.outbox_message import OutboxMessage
from indexing_service.domain.entities.embedding_request import EmbeddingRequest

EVENT_TYPE = "embedding.documents.requested.v1"
EVENT_VERSION = "1.0"
AGGREGATE_TYPE = "embedding_job"
PRODUCER = "read-model-builder"


def build_command_data(
    request: EmbeddingRequest,
    *,
    model: str | None,
    return_dense: bool = True,
    return_sparse: bool = True,
) -> dict[str, Any]:
    """Строит тело ``data`` команды (порядок ``items`` сохраняется)."""
    data: dict[str, Any] = {
        "request_id": str(request.request_id.value),
        "return_dense": return_dense,
        "return_sparse": return_sparse,
        "items": [
            {"text_id": item.text_id, "text": item.text}
            for item in request.items
        ],
    }
    if model is not None:
        data["model"] = model
    return data


def build_command_message(
    request: EmbeddingRequest,
    *,
    model: str | None,
    message_id: UUID,
    occurred_at: datetime,
    return_dense: bool = True,
    return_sparse: bool = True,
    trace_id: str | None = None,
    next_attempt_at: datetime | None = None,
) -> OutboxMessage:
    """Собирает ``OutboxMessage`` с конвертом команды в ``payload``.

    Args:
        request: Команда на эмбеддинг (корреляция по ``request_id``).
        model: Ожидаемый ключ модели или ``None`` (embedding-service возьмёт
            модель по умолчанию).
        message_id: ``event_id`` конверта (uuidv7).
        occurred_at: Доменное время постановки команды.
        return_dense: Запрашивать dense-векторы.
        return_sparse: Запрашивать sparse-векторы.
        trace_id: W3C traceparent для сквозной трассировки (опционально).
        next_attempt_at: Отложенная публикация (backoff ретрая) или ``None``.

    Returns:
        Строка outbox с self-contained конвертом команды.
    """
    envelope: dict[str, Any] = {
        "event_id": str(message_id),
        "event_type": EVENT_TYPE,
        "event_version": EVENT_VERSION,
        "aggregate_type": AGGREGATE_TYPE,
        "aggregate_id": str(request.request_id.value),
        "occurred_at": occurred_at.isoformat(),
        "producer": PRODUCER,
        "data": build_command_data(
            request,
            model=model,
            return_dense=return_dense,
            return_sparse=return_sparse,
        ),
    }
    if trace_id is not None:
        envelope["trace_id"] = trace_id
    return OutboxMessage(
        id=message_id,
        aggregate_type="embedding_request",
        aggregate_id=request.request_id.value,
        event_type=EVENT_TYPE,
        payload=envelope,
        occurred_at=occurred_at,
        headers={"trace_id": trace_id} if trace_id is not None else {},
        next_attempt_at=next_attempt_at,
    )
