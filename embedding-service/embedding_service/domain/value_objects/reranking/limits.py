"""Value object ``RerankLimits`` — политика лимитов rerank-запроса."""

from dataclasses import dataclass

from embedding_service.domain.exceptions import InvalidLimitsError


@dataclass(frozen=True, slots=True)
class RerankLimits:
    """Структурные лимиты одного rerank-запроса.

    Все значения должны быть строго положительны.

    Attributes:
        max_documents: Максимум документов-кандидатов в запросе.
        max_query_chars: Максимум символов в тексте запроса.
        max_document_chars: Максимум символов в одном документе.
        max_total_bytes: Максимум суммарного размера (UTF-8 байт).
    """

    max_documents: int
    max_query_chars: int
    max_document_chars: int
    max_total_bytes: int

    def __post_init__(self) -> None:
        limits = {
            "max_documents": self.max_documents,
            "max_query_chars": self.max_query_chars,
            "max_document_chars": self.max_document_chars,
            "max_total_bytes": self.max_total_bytes,
        }
        for name, value in limits.items():
            if value <= 0:
                raise InvalidLimitsError(f"{name} должно быть > 0: {value}")
