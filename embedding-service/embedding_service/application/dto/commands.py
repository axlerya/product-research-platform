"""DTO входов use cases и выхода документного use case (frozen dataclass)."""

from dataclasses import dataclass

from embedding_service.domain.value_objects.item_result import (
    EmbeddingItemResult,
)
from embedding_service.domain.value_objects.request_item import (
    EmbeddingRequestItem,
)


@dataclass(frozen=True, slots=True)
class EmbedDocumentsCommand:
    """Вход U1 ``EmbedDocuments`` (из RabbitMQ-конверта).

    Attributes:
        request_id: Ключ идемпотентности/корреляции.
        items: Элементы батча в порядке входа.
        return_dense: Запросить dense-вектор.
        return_sparse: Запросить sparse-вектор.
    """

    request_id: str
    items: tuple[EmbeddingRequestItem, ...]
    return_dense: bool
    return_sparse: bool


@dataclass(frozen=True, slots=True)
class EmbedQueryQuery:
    """Вход U2 ``EmbedQuery`` (из gRPC ``EmbedQueryRequest``)."""

    text: str
    request_id: str | None


@dataclass(frozen=True, slots=True)
class EmbedQueriesQuery:
    """Вход U3 ``EmbedQueries`` (из gRPC ``EmbedQueriesRequest``)."""

    texts: tuple[str, ...]
    request_id: str | None


@dataclass(frozen=True, slots=True)
class DocumentsGenerated:
    """Выход U1 — публикуется presentation как ``generated.v1``.

    Attributes:
        request_id: Дословно из команды (корреляция).
        model_key: ``model_version`` на проводе (== ``EmbeddingModelId.key``).
        dim: Размерность dense (для bge-m3 — 1024).
        results: Пер-элементные результаты в порядке ``items`` команды.
    """

    request_id: str
    model_key: str
    dim: int
    results: tuple[EmbeddingItemResult, ...]
