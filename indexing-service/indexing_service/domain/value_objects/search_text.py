"""Value object ``SearchText`` — составной текст документа для эмбеддинга."""

from dataclasses import dataclass

from indexing_service.domain.exceptions import InvalidDocumentError


@dataclass(frozen=True, slots=True)
class SearchText:
    """Готовый текст, из которого считаются dense и sparse векторы.

    Attributes:
        value: Непустой составной текст (name+brand+category+description).
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise InvalidDocumentError("Текст документа не может быть пустым")
