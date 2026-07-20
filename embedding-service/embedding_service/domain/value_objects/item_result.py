"""Value object ``EmbeddingItemResult`` — результат по одному элементу."""

from dataclasses import dataclass
from typing import Self

from embedding_service.domain.exceptions import InvalidVectorError
from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.item_error import ItemError
from embedding_service.domain.value_objects.text_id import TextId
from embedding_service.domain.value_objects.token_count import TokenCount


@dataclass(frozen=True, slots=True)
class EmbeddingItemResult:
    """Итог по одному элементу батча (несущий элемент партиала).

    Инвариант: ровно одно из ``embedding``/``error`` задано.

    Attributes:
        text_id: Идентификатор элемента (порядок/корреляция).
        embedding: Эмбеддинг при успехе, иначе ``None``.
        token_count: Число токенов при успехе, иначе ``None``.
        error: Описание отказа при неуспехе, иначе ``None``.
    """

    text_id: TextId
    embedding: Embedding | None = None
    token_count: TokenCount | None = None
    error: ItemError | None = None

    def __post_init__(self) -> None:
        if (self.embedding is not None) == (self.error is not None):
            raise InvalidVectorError(
                "Ровно одно из embedding/error должно быть задано"
            )

    @property
    def is_ok(self) -> bool:
        """Успешен ли элемент."""
        return self.embedding is not None

    @classmethod
    def ok(
        cls, text_id: TextId, embedding: Embedding, token_count: TokenCount
    ) -> Self:
        """Успешный результат."""
        return cls(
            text_id=text_id, embedding=embedding, token_count=token_count
        )

    @classmethod
    def failed(cls, text_id: TextId, error: ItemError) -> Self:
        """Отказ по элементу (партиал)."""
        return cls(text_id=text_id, error=error)
