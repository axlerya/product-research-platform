"""Value object ``RerankCandidate`` — документ-кандидат для ранжирования."""

from dataclasses import dataclass

from embedding_service.domain.exceptions import EmptyTextError
from embedding_service.domain.value_objects.text_id import TextId


@dataclass(frozen=True, slots=True)
class RerankCandidate:
    """Документ-кандидат: идентификатор + текст.

    Отвергается пустой/пробельный текст; лимиты длины — политика
    ``RerankLimits`` (проверяются в ``RerankValidator``).

    Attributes:
        text_id: Идентификатор документа (корреляция/порядок).
        text: Текст документа.
    """

    text_id: TextId
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise EmptyTextError("Текст документа не может быть пустым")

    @property
    def char_length(self) -> int:
        """Длина документа в символах."""
        return len(self.text)
