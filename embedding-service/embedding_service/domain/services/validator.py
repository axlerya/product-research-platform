"""Доменный сервис ``EmbeddingValidator`` — батч-обёртка над инвариантами."""

from collections.abc import Sequence

from embedding_service.domain.exceptions import InvalidVectorError
from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)


class EmbeddingValidator:
    """Fail-fast проверка коллекции ``Embedding`` перед сборкой.

    Новых правил не вводит — прогоняет по всему батчу инварианты, уже
    гарантированные конструкторами VO (размерность dense, единая модель),
    для ранней диагностики дефекта провайдера.
    """

    @staticmethod
    def validate_batch(
        embeddings: Sequence[Embedding],
        *,
        expected_dim: int,
        model_id: EmbeddingModelId,
    ) -> None:
        """Проверяет, что все эмбеддинги согласованы с ожидаемой моделью.

        Args:
            embeddings: Эмбеддинги батча.
            expected_dim: Ожидаемая размерность dense (для bge-m3 — 1024).
            model_id: Ожидаемый идентификатор модели.

        Raises:
            InvalidVectorError: Если размерность dense или модель какого-то
                эмбеддинга не совпадает с ожидаемыми.
        """
        for index, embedding in enumerate(embeddings):
            if embedding.dense.dimension != expected_dim:
                raise InvalidVectorError(
                    f"Элемент {index}: размерность dense "
                    f"{embedding.dense.dimension} != {expected_dim}"
                )
            if embedding.model_id != model_id:
                raise InvalidVectorError(
                    f"Элемент {index}: чужая модель {embedding.model_id.key}"
                )
