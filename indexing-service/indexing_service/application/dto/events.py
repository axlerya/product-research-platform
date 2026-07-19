"""DTO событий каталога — разобранный конверт (§3.3).

Presentation парсит wire-конверт (Pydantic, tolerant) и маппит в эти
DTO: деньги-строки → ``Decimal``. Каждое событие несёт свой ``kind``
(доменный вид изменения).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.domain.services.change_classifier import ChangeKind


@dataclass(frozen=True, slots=True)
class ProductCreatedEvent:
    """Создание товара — полный снимок (§1.4)."""

    event_id: UUID
    occurred_at: datetime
    product: ProductSnapshot

    kind = ChangeKind.CREATED

    @property
    def product_id(self) -> UUID:
        """Идентификатор товара (из снимка)."""
        return self.product.product_id

    @property
    def aggregate_version(self) -> int:
        """Версия агрегата (из снимка)."""
        return self.product.aggregate_version


@dataclass(frozen=True, slots=True)
class ContentChangedEvent:
    """Изменение контент-группы (name/description/category/brand)."""

    event_id: UUID
    occurred_at: datetime
    product_id: UUID
    sku: str
    aggregate_version: int
    changed_fields: tuple[str, ...]
    name: str
    description: str
    category: str
    brand: str

    kind = ChangeKind.CONTENT_CHANGED


@dataclass(frozen=True, slots=True)
class CommercialChangedEvent:
    """Изменение коммерческой группы (price/cost/stock/supplier)."""

    event_id: UUID
    occurred_at: datetime
    product_id: UUID
    sku: str
    aggregate_version: int
    changed_fields: tuple[str, ...]
    price: Decimal
    cost: Decimal
    currency: str
    stock: int
    supplier: str

    kind = ChangeKind.COMMERCIAL_CHANGED


@dataclass(frozen=True, slots=True)
class ProductDeletedEvent:
    """Мягкое удаление товара."""

    event_id: UUID
    occurred_at: datetime
    product_id: UUID
    sku: str
    aggregate_version: int

    kind = ChangeKind.DELETED


CatalogEvent = (
    ProductCreatedEvent
    | ContentChangedEvent
    | CommercialChangedEvent
    | ProductDeletedEvent
)
