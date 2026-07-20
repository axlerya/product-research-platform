"""Value object ``Embedding`` — dense + sparse + идентификатор модели."""

from dataclasses import dataclass

from embedding_service.domain.exceptions import InvalidVectorError
from embedding_service.domain.value_objects.dense_vector import DenseVector
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.sparse_vector import SparseVector


@dataclass(frozen=True, slots=True)
class Embedding:
    """Результат эмбеддинга одного текста.

    Гарантирует, что размерность dense-вектора соответствует модели
    (проверка размерности dense).

    Attributes:
        dense: Плотный вектор.
        sparse: Разрежённый вектор.
        model_id: Идентификатор породившей модели.
    """

    dense: DenseVector
    sparse: SparseVector
    model_id: EmbeddingModelId

    def __post_init__(self) -> None:
        if self.dense.dimension != self.model_id.dim:
            raise InvalidVectorError(
                f"Размерность dense ({self.dense.dimension}) не совпадает "
                f"с моделью ({self.model_id.dim})"
            )
