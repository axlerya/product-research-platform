"""Value object ``EmbeddingModelId`` — идентификатор версии модели."""

from dataclasses import dataclass

from embedding_service.domain.exceptions import InvalidModelIdError


@dataclass(frozen=True, slots=True)
class EmbeddingModelId:
    """Стабильный идентификатор модели эмбеддингов.

    Свойство ``key`` — строковый ``model_version`` на проводе; его смена
    означает несопоставимость векторов и триггерит переиндексацию у
    потребителя.

    Attributes:
        name: Имя модели, например ``"BAAI/bge-m3"``.
        revision: Ревизия/commit-sha весов.
        pooling: Способ пулинга (``"cls"``/``"mean"``).
        normalized: Нормированы ли dense-векторы (L2).
        dim: Размерность dense-вектора.
    """

    name: str
    revision: str
    pooling: str
    normalized: bool
    dim: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidModelIdError("Имя модели не может быть пустым")
        if self.dim <= 0:
            raise InvalidModelIdError(
                f"Размерность должна быть > 0: {self.dim}"
            )

    @property
    def key(self) -> str:
        """Каноническая строка модели (``model_version`` на проводе)."""
        norm = 1 if self.normalized else 0
        return (
            f"{self.name}@{self.revision}"
            f"|pool={self.pooling}|norm={norm}|dim={self.dim}"
        )
