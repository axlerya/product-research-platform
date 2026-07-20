"""Доменные enum'ы: статусы job/request/chunk, действие, коды ошибок.

``EmbeddingErrorCode`` дословно повторяет коды ошибок в событии-результате
``embedding.documents.generated.v1`` (embedding-service §5.3).
"""

from enum import StrEnum


class JobStatus(StrEnum):
    """Статус indexing job (§8 REFACTOR_PLAN)."""

    PENDING = "pending"
    AWAITING = "awaiting"
    PARTIALLY_FAILED = "partially_failed"
    DONE = "done"
    FAILED = "failed"


class RequestStatus(StrEnum):
    """Статус команды на эмбеддинг (embedding_request)."""

    PENDING = "pending"
    AWAITING = "awaiting"
    DONE = "done"
    FAILED = "failed"


class ChunkStatus(StrEnum):
    """Статус отдельного чанка внутри job."""

    PENDING = "pending"
    OK = "ok"
    RETRYING = "retrying"
    FAILED = "failed"


class IndexAction(StrEnum):
    """Что делает job с векторами."""

    FULL_INDEX = "full_index"
    REEMBED = "reembed"


class EmbeddingErrorCode(StrEnum):
    """Коды item-ошибок из события-результата embedding-service."""

    EMPTY_TEXT = "EMPTY_TEXT"
    TEXT_TOO_LONG = "TEXT_TOO_LONG"
    TOKENS_EXCEEDED = "TOKENS_EXCEEDED"
    INFERENCE_FAILED = "INFERENCE_FAILED"
