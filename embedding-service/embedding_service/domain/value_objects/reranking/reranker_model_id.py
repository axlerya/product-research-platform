"""Value object ``RerankerModelId`` — идентификатор версии reranker-модели."""

from dataclasses import dataclass

from embedding_service.domain.exceptions import InvalidModelIdError


@dataclass(frozen=True, slots=True)
class RerankerModelId:
    """Стабильный идентификатор reranker-модели.

    Свойство ``key`` — строковый ``model_version`` на проводе (водяной знак
    модели). Флаг ``normalized`` влияет на семантику скора (сигмоида →
    ``[0, 1]``), поэтому входит в ключ.

    Attributes:
        name: Имя модели, например ``"BAAI/bge-reranker-v2-m3"``.
        revision: Ревизия/commit-sha весов.
        normalized: Нормируется ли скор в ``[0, 1]`` (сигмоида).
    """

    name: str
    revision: str
    normalized: bool

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidModelIdError("Имя модели не может быть пустым")

    @property
    def key(self) -> str:
        """Каноническая строка модели (``model_version`` на проводе)."""
        norm = 1 if self.normalized else 0
        return f"{self.name}@{self.revision}|norm={norm}"
