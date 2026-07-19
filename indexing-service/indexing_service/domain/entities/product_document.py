"""Сущность ``ProductDocument`` — поисковая проекция товара.

Иммутабельный снимок состояния товара, восстанавливаемый из события или
REST-снимка catalog. Знает, как построить свой текст для эмбеддинга и
маржу, но не умеет эмбеддить и писать в Qdrant (это порты).
"""

from dataclasses import dataclass
from datetime import date

from indexing_service.domain.exceptions import InvalidDocumentError
from indexing_service.domain.services.document_composer import compose
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.margin import Margin
from indexing_service.domain.value_objects.metrics import ProductMetrics
from indexing_service.domain.value_objects.pricing import Pricing
from indexing_service.domain.value_objects.search_text import SearchText
from indexing_service.domain.value_objects.sku import Sku
from indexing_service.domain.value_objects.stock import StockLevel


@dataclass(frozen=True, slots=True)
class ProductDocument:
    """Проекция товара, готовая к индексации.

    Attributes:
        product_id: Идентификатор товара (= id точки Qdrant).
        sku: Артикул.
        name: Название.
        description: Описание.
        category: Имя категории.
        brand: Имя бренда.
        supplier: Имя поставщика.
        pricing: Цена и себестоимость.
        stock: Остаток на складе.
        metrics: Метрики (только из ``created``/reconcile; иначе ``None``).
        source_updated_at: Дата последнего обновления в источнике.
        aggregate_version: Версия агрегата товара (>= 1).
    """

    product_id: ProductId
    sku: Sku
    name: str
    description: str
    category: str
    brand: str
    supplier: str
    pricing: Pricing
    stock: StockLevel
    metrics: ProductMetrics | None
    source_updated_at: date | None
    aggregate_version: int

    def __post_init__(self) -> None:
        if self.aggregate_version < 1:
            raise InvalidDocumentError(
                f"Версия агрегата должна быть >= 1: {self.aggregate_version}"
            )
        if not self.name.strip():
            raise InvalidDocumentError("Название товара не может быть пустым")

    def search_text(self) -> SearchText:
        """Составной текст документа для эмбеддинга."""
        return compose(
            name=self.name,
            brand=self.brand,
            category=self.category,
            description=self.description,
        )

    def margin(self) -> Margin:
        """Маржа товара (детерминированный расчёт)."""
        return self.pricing.calculate_margin()

    def content_hash(self) -> ContentHash:
        """Хэш текста документа (для детекта смены контента)."""
        return ContentHash.of(self.search_text().value)
