"""DTO ``ProductSnapshot`` — полный снимок товара из REST catalog.

Используется repair/reindex/reconcile. Деньги — ``Decimal`` (никогда
float); валюта — строкой; ``product_id`` — сырой ``UUID``.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProductSnapshot:
    """Денормализованный снимок товара (как в ``GET /products/{id}``).

    Attributes:
        product_id: Идентификатор товара.
        sku: Артикул.
        name: Название.
        description: Описание.
        category: Имя категории.
        brand: Имя бренда.
        supplier: Имя поставщика.
        price: Цена.
        cost: Себестоимость.
        currency: Код валюты (ISO-4217 alpha-3).
        stock: Остаток на складе.
        sales_per_month: Продажи за месяц.
        avg_rating: Средний рейтинг.
        review_count: Число отзывов.
        source_updated_at: Дата последнего обновления в источнике.
        aggregate_version: Версия агрегата товара.
    """

    product_id: UUID
    sku: str
    name: str
    description: str
    category: str
    brand: str
    supplier: str
    price: Decimal
    cost: Decimal
    currency: str
    stock: int
    sales_per_month: int
    avg_rating: Decimal
    review_count: int
    source_updated_at: date | None
    aggregate_version: int
