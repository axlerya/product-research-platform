"""Доменный сервис ``EmbeddingAssembler`` — сборка результата по порядку."""

from collections.abc import Sequence

from embedding_service.domain.exceptions import InvalidVectorError
from embedding_service.domain.value_objects.batch_result import (
    BatchEmbeddingResult,
)
from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.item_error import ItemError
from embedding_service.domain.value_objects.item_result import (
    EmbeddingItemResult,
)
from embedding_service.domain.value_objects.text_id import TextId
from embedding_service.domain.value_objects.token_count import TokenCount

# Исход по элементу: успех ``(Embedding, TokenCount)`` либо отказ ``ItemError``.
Outcome = tuple[Embedding, TokenCount] | ItemError


class EmbeddingAssembler:
    """Сборка ``BatchEmbeddingResult`` строгим ``zip`` по порядку входа."""

    @staticmethod
    def assemble(
        text_ids: Sequence[TextId],
        outcomes: Sequence[Outcome],
        model_id: EmbeddingModelId,
    ) -> BatchEmbeddingResult:
        """Сшивает ``text_ids[i]`` с ``outcomes[i]`` в порядке входа.

        Args:
            text_ids: Идентификаторы элементов в порядке входа.
            outcomes: Пер-элементные исходы (успех/отказ) в том же порядке.
            model_id: Идентификатор породившей модели.

        Returns:
            Упорядоченный результат батча.

        Raises:
            InvalidVectorError: Если длины ``text_ids`` и ``outcomes`` не
                совпадают.
        """
        if len(text_ids) != len(outcomes):
            raise InvalidVectorError(
                f"Длины text_ids ({len(text_ids)}) и outcomes "
                f"({len(outcomes)}) не совпадают"
            )
        items = tuple(
            _to_item(text_id, outcome)
            for text_id, outcome in zip(text_ids, outcomes, strict=True)
        )
        return BatchEmbeddingResult(model_id=model_id, items=items)


def _to_item(text_id: TextId, outcome: Outcome) -> EmbeddingItemResult:
    if isinstance(outcome, ItemError):
        return EmbeddingItemResult.failed(text_id, outcome)
    embedding, token_count = outcome
    return EmbeddingItemResult.ok(text_id, embedding, token_count)
