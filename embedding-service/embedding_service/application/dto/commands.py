"""DTO входов use cases и выхода документного use case (frozen dataclass)."""

from dataclasses import dataclass

from embedding_service.domain.value_objects.item_result import (
    EmbeddingItemResult,
)


@dataclass(frozen=True, slots=True)
class RawTextItem:
    """Сырой элемент документного батча (до доменной валидации).

    Тексты приходят строками с провода; валидация и построение VO —
    в use case ``EmbedDocuments`` (иначе невозможен партиал per-item).

    Attributes:
        text_id: Непрозрачный идентификатор элемента (корреляция/порядок).
        text: Сырой текст документа.
    """

    text_id: str
    text: str


@dataclass(frozen=True, slots=True)
class EmbedDocumentsCommand:
    """Вход U1 ``EmbedDocuments`` (из RabbitMQ-конверта).

    Attributes:
        request_id: Ключ идемпотентности/корреляции.
        items: Сырые элементы батча в порядке входа.
        return_dense: Запросить dense-вектор.
        return_sparse: Запросить sparse-вектор.
    """

    request_id: str
    items: tuple[RawTextItem, ...]
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
