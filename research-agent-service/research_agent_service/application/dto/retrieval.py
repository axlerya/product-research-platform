"""DTO retrieval-пайплайна: эмбеддинг → Qdrant (RRF) → rerank → ответ."""

from dataclasses import dataclass
from decimal import Decimal

from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.money import Money


@dataclass(frozen=True, slots=True)
class QueryEmbedding:
    """Dense+sparse эмбеддинг запроса из embedding-service."""

    dense: tuple[float, ...]
    sparse_indices: tuple[int, ...]
    sparse_values: tuple[float, ...]
    model_version: str
    token_count: int


@dataclass(frozen=True, slots=True)
class RetrievedPoint:
    """Точка из Qdrant после серверного RRF (поисковая read-model).

    Цена/остаток/маржа — из payload (fallback, если catalog недоступен);
    авторитетные значения приходят из catalog при обогащении.
    """

    product_id: str
    sku: str
    name: str
    description: str
    category: str
    currency: str
    score: float
    price: Decimal | None = None
    stock: int | None = None
    in_stock: bool | None = None
    margin_percent: Decimal | None = None


@dataclass(frozen=True, slots=True)
class RerankDocument:
    """Кандидат на переранжирование: непрозрачный id и текст."""

    id: str
    text: str


@dataclass(frozen=True, slots=True)
class RankedDoc:
    """Отранжированный документ: id, исходная позиция, скор."""

    id: str
    index: int
    score: Decimal


@dataclass(frozen=True, slots=True)
class RankedProduct:
    """Итоговый товар в контексте ответа (после rerank и обогащения)."""

    sku: str
    name: str
    category: str
    snippet: str
    price: Money | None = None
    stock: int | None = None
    in_stock: bool | None = None
    margin_percent: Decimal | None = None
    rerank_score: Decimal | None = None
    price_authoritative: bool = False


@dataclass(frozen=True, slots=True)
class RagContext:
    """Результат product_catalog_rag: товары, источники и деградации."""

    products: tuple[RankedProduct, ...]
    citations: tuple[Citation, ...]
    degradations: tuple[Degradation, ...] = ()
