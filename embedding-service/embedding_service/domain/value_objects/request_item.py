"""Value object ``EmbeddingRequestItem`` — элемент входного батча."""

from dataclasses import dataclass

from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.domain.value_objects.text_id import TextId


@dataclass(frozen=True, slots=True)
class EmbeddingRequestItem:
    """Пара «идентификатор + текст» одного элемента батча.

    Attributes:
        text_id: Идентификатор для корреляции/порядка.
        text: Текст для эмбеддинга.
    """

    text_id: TextId
    text: EmbeddingText
