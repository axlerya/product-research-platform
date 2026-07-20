"""Value object ``RerankQuery`` — текст запроса для reranking."""

from dataclasses import dataclass

from embedding_service.domain.exceptions import EmptyTextError


@dataclass(frozen=True, slots=True)
class RerankQuery:
    """Текст запроса, относительно которого ранжируются документы.

    Отвергается пустой/пробельный текст; лимиты длины — политика
    ``RerankLimits`` (проверяются в ``RerankValidator``).

    Attributes:
        value: Текст запроса.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise EmptyTextError("Текст запроса не может быть пустым")

    @property
    def char_length(self) -> int:
        """Длина запроса в символах."""
        return len(self.value)
