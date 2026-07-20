"""Сущность ``EmbeddingRequest`` — одна команда на эмбеддинг (§8).

Дочерняя к ``IndexingJob``: оригинал + каждый ретрай/rechunk — отдельная
команда со своим детерминированным ``request_id``. Несёт подмножество
чанков job с готовым текстом (для повторной публикации без пересчёта).
"""

from dataclasses import dataclass
from datetime import datetime

from indexing_service.domain.exceptions import InvalidRequestError
from indexing_service.domain.value_objects.identifiers import JobId, RequestId
from indexing_service.domain.value_objects.job_status import RequestStatus


@dataclass(frozen=True, slots=True)
class RequestItem:
    """Элемент команды: текст документа под своим ``text_id``.

    Attributes:
        text_id: Идентификатор элемента (== id точки Qdrant).
        text: Готовый текст документа для эмбеддинга.
    """

    text_id: str
    text: str

    def __post_init__(self) -> None:
        if not self.text_id:
            raise InvalidRequestError("text_id элемента не может быть пустым")


@dataclass(frozen=True, slots=True)
class EmbeddingRequest:
    """Команда на эмбеддинг (embedding_request).

    Attributes:
        request_id: Детерминированный идентификатор команды.
        job_id: Родительское задание.
        attempt: Номер попытки (0 — оригинал).
        items: Элементы команды (>= 1, порядок сохраняется).
        status: Статус команды.
        next_attempt_at: Момент следующего ретрая (backoff) или ``None``.
        created_at/requested_at/received_at: Времена жизни.
    """

    request_id: RequestId
    job_id: JobId
    attempt: int
    items: tuple[RequestItem, ...]
    status: RequestStatus
    next_attempt_at: datetime | None
    created_at: datetime
    requested_at: datetime | None
    received_at: datetime | None

    def __post_init__(self) -> None:
        if self.attempt < 0:
            raise InvalidRequestError(f"attempt < 0: {self.attempt}")
        if not self.items:
            raise InvalidRequestError("команда должна нести хотя бы элемент")
