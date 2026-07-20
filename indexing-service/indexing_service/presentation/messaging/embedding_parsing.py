"""Разбор конверта embedding → DTO ``EmbeddingResult`` (§7, tolerant).

Читаем только поля, которые используем; неизвестные — игнорируем. Неверный
тип, битый ``data`` или неизвестный код ошибки → ``EventValidationError``
(poison → DLQ на стороне консюмера, шаг 4).
"""

from typing import Any
from uuid import UUID

from indexing_service.application.dto.embedding_result import (
    EmbeddingResult,
    EmbeddingResultItem,
    ItemError,
    SparseData,
)
from indexing_service.application.exceptions import EventValidationError
from indexing_service.domain.value_objects.job_status import EmbeddingErrorCode
from indexing_service.presentation.messaging.embedding_schemas import (
    EmbeddingEventEnvelope,
)

GENERATED = "embedding.documents.generated.v1"

_PARSE_ERRORS = (KeyError, TypeError, ValueError)


def parse_embedding_result(
    envelope: EmbeddingEventEnvelope,
) -> EmbeddingResult:
    """Маппит конверт события-результата в ``EmbeddingResult``.

    Raises:
        EventValidationError: Неизвестный тип, неразбираемый ``data`` или
            неизвестный код ошибки (poison → DLQ).
    """
    if envelope.event_type != GENERATED:
        raise EventValidationError(
            f"неизвестный тип события: {envelope.event_type}"
        )
    try:
        return _parse(envelope.data)
    except _PARSE_ERRORS as exc:
        raise EventValidationError(
            f"не удалось разобрать {GENERATED}: {exc}"
        ) from exc


def _parse(data: dict[str, Any]) -> EmbeddingResult:
    return EmbeddingResult(
        request_id=UUID(str(data["request_id"])),
        model_version=str(data["model_version"]),
        dim=int(data["dim"]),
        items=tuple(_item(result) for result in data["results"]),
    )


def _item(result: dict[str, Any]) -> EmbeddingResultItem:
    text_id = result["text_id"]
    status = result["status"]
    if status == "error":
        error = result["error"]
        return EmbeddingResultItem(
            text_id=text_id,
            dense=None,
            sparse=None,
            token_count=None,
            error=ItemError(
                code=EmbeddingErrorCode(error["code"]),
                message=str(error.get("message", "")),
            ),
        )
    if status != "ok":
        raise ValueError(f"неизвестный status элемента: {status!r}")
    dense = result.get("dense")
    token_count = result.get("token_count")
    return EmbeddingResultItem(
        text_id=text_id,
        dense=tuple(float(value) for value in dense) if dense else None,
        sparse=_sparse(result.get("sparse")),
        token_count=int(token_count) if token_count is not None else None,
        error=None,
    )


def _sparse(sparse: dict[str, Any] | None) -> SparseData | None:
    if not sparse:
        return None
    return SparseData(
        indices=tuple(int(index) for index in sparse["indices"]),
        values=tuple(float(value) for value in sparse["values"]),
    )
