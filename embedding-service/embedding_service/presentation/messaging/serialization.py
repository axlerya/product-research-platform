"""Сериализация результата U1 в конверт события generated.v1 (§5.3)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from embedding_service.application.dto import DocumentsGenerated
from embedding_service.domain.value_objects.item_result import (
    EmbeddingItemResult,
)
from embedding_service.presentation.messaging.schemas import RequestedEnvelope
from embedding_service.presentation.messaging.topology import GENERATED_RK

_PRODUCER = "embedding-service"


def to_generated_envelope(
    request: RequestedEnvelope,
    result: DocumentsGenerated,
    *,
    event_id: UUID,
    occurred_at: datetime,
) -> dict[str, Any]:
    """Строит платформенный конверт события-результата."""
    envelope: dict[str, Any] = {
        "event_id": str(event_id),
        "event_type": GENERATED_RK,
        "event_version": "1.0",
        "aggregate_type": "embedding_job",
        "aggregate_id": result.request_id,
        "occurred_at": _rfc3339(occurred_at),
        "producer": _PRODUCER,
        "data": {
            "request_id": result.request_id,
            "model_version": result.model_key,
            "dim": result.dim,
            "results": [
                _result_to_wire(item, request) for item in result.results
            ],
        },
    }
    if request.trace_id is not None:
        envelope["trace_id"] = request.trace_id
    if request.correlation_id is not None:
        envelope["correlation_id"] = request.correlation_id
    return envelope


def _result_to_wire(
    item: EmbeddingItemResult, request: RequestedEnvelope
) -> dict[str, Any]:
    if not item.is_ok:
        return {
            "text_id": item.text_id.value,
            "status": "error",
            "error": {
                "code": item.error.code.value,
                "message": item.error.message,
            },
        }
    wire: dict[str, Any] = {"text_id": item.text_id.value, "status": "ok"}
    if request.data.return_dense:
        wire["dense"] = list(item.embedding.dense.values)
    if request.data.return_sparse:
        wire["sparse"] = {
            "indices": list(item.embedding.sparse.indices),
            "values": list(item.embedding.sparse.values),
        }
    wire["token_count"] = item.token_count.value
    return wire


def _rfc3339(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
