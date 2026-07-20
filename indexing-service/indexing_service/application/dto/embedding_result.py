"""DTO результата эмбеддинга — разобранное событие ``generated`` (§1, §6).

Tolerant-разбор ``embedding.documents.generated.v1``. Корреляция по
``request_id``; порядок ``items`` == порядку команды. Item может быть
успешным (dense/sparse/token_count — по запрошенным ``return_*``) или
ошибочным (код из закрытого набора embedding-service). Маппинг в доменный
``Embedding`` и запись в Qdrant — уже в ``ApplyEmbeddingResult`` (шаг 4).
"""

from dataclasses import dataclass
from uuid import UUID

from indexing_service.domain.value_objects.job_status import EmbeddingErrorCode


@dataclass(frozen=True, slots=True)
class SparseData:
    """Sparse-вектор в проводном виде (COO: индексы + значения)."""

    indices: tuple[int, ...]
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ItemError:
    """Ошибка эмбеддинга одного элемента."""

    code: EmbeddingErrorCode
    message: str


@dataclass(frozen=True, slots=True)
class EmbeddingResultItem:
    """Результат по одному ``text_id`` (успех либо ошибка).

    Attributes:
        text_id: Идентификатор элемента (== id точки Qdrant).
        dense: Плотный вектор или ``None`` (если не запрошен/ошибка).
        sparse: Разреженный вектор или ``None``.
        token_count: Число токенов или ``None``.
        error: Ошибка или ``None`` (успех).
    """

    text_id: str
    dense: tuple[float, ...] | None
    sparse: SparseData | None
    token_count: int | None
    error: ItemError | None

    @property
    def is_ok(self) -> bool:
        """Успешен ли элемент (нет ошибки)."""
        return self.error is None


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Разобранное событие-результат по одной команде.

    Attributes:
        request_id: Идентификатор команды (корреляция с ``EmbeddingRequest``).
        model_version: Ключ модели embedding-service (водяной знак).
        dim: Размерность dense-вектора.
        items: Результаты по элементам (порядок == команде).
    """

    request_id: UUID
    model_version: str
    dim: int
    items: tuple[EmbeddingResultItem, ...]
