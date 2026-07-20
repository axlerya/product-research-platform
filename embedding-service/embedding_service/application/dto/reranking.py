"""DTO входа use case ``RerankDocuments`` (frozen dataclass).

Изолировано от документного/запросного эмбеддинга: свой модуль, не трогает
``application.dto.commands``.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RerankInputDocument:
    """Сырой документ-кандидат (до доменной валидации).

    Приходит строками с провода (gRPC ``RerankDocument``); построение VO и
    валидация — в use case ``RerankDocuments``.

    Attributes:
        text_id: Непрозрачный идентификатор документа (корреляция).
        text: Сырой текст документа.
    """

    text_id: str
    text: str


@dataclass(frozen=True, slots=True)
class RerankDocumentsCommand:
    """Вход ``RerankDocuments`` (из gRPC ``RerankRequest``).

    Attributes:
        query: Текст запроса, относительно которого ранжируются документы.
        documents: Документы-кандидаты в порядке входа.
        top_n: Сколько верхних результатов вернуть; ``None`` — все.
    """

    query: str
    documents: tuple[RerankInputDocument, ...]
    top_n: int | None
