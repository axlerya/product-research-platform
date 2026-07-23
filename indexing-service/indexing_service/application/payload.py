"""Сборка payload точки Qdrant из домена (§4.4).

Деньги — ``float`` (Qdrant ``Range`` фильтрует по числу; точный ``Decimal``
остаётся в catalog). Значения — плоские типы, чтобы адаптер Qdrant был
humble object и просто передавал dict.
"""

from datetime import date, datetime
from decimal import Decimal

from indexing_service.domain.entities.product_document import ProductDocument
from indexing_service.domain.value_objects.pricing import Pricing
from indexing_service.domain.value_objects.stock import StockLevel


def _opt_float(value: Decimal | None) -> float | None:
    """Переводит ``Decimal`` в ``float`` (или ``None``)."""
    return float(value) if value is not None else None


def _opt_date(value: date | None) -> str | None:
    """ISO-строка даты (или ``None``)."""
    return value.isoformat() if value is not None else None


def full_payload(
    document: ProductDocument, *, model_version: str, indexed_at: datetime
) -> dict[str, object]:
    """Полный payload для upsert (created/repair)."""
    margin = document.margin()
    metrics = document.metrics
    pricing = document.pricing
    return {
        "product_id": str(document.product_id.value),
        "sku": document.sku.value,
        "name": document.name,
        "description": document.description,
        "category": document.category,
        "brand": document.brand,
        "supplier": document.supplier,
        "price": float(pricing.price.amount),
        "cost": float(pricing.cost.amount),
        "currency": pricing.price.currency.code,
        "stock": document.stock.quantity,
        "in_stock": document.stock.is_in_stock,
        "margin_percent": _opt_float(margin.percent),
        "sales_per_month": metrics.sales_per_month if metrics else None,
        "rating": _opt_float(metrics.avg_rating.value) if metrics else None,
        "review_count": metrics.review_count if metrics else None,
        "source_updated_at": _opt_date(document.source_updated_at),
        "aggregate_version": document.aggregate_version,
        "model_version": model_version,
        "content_hash": document.content_hash().value,
        "indexed_at": indexed_at.isoformat(),
        "is_deleted": False,
    }


def pending_payload(
    document: ProductDocument, *, indexed_at: datetime
) -> dict[str, object]:
    """Полный payload товара ДО эмбеддинга (фаза A, §9.4).

    Водяные знаки текста и модели (``content_hash``, ``model_version``) сюда
    не входят: их пишет только тот, кто реально посчитал векторы. Иначе
    точка объявила бы текст проиндексированным раньше времени, и дедуп
    ``classify`` навсегда закрыл бы товару путь к ре-эмбеддингу.
    """
    payload = full_payload(document, model_version="", indexed_at=indexed_at)
    del payload["model_version"]
    del payload["content_hash"]
    return payload


def content_payload(
    *,
    name: str,
    description: str,
    category: str,
    brand: str,
    content_hash: str,
    model_version: str,
    aggregate_version: int,
    indexed_at: datetime,
) -> dict[str, object]:
    """Частичный payload для set_payload после ре-эмбеддинга (§6.3)."""
    return {
        "name": name,
        "description": description,
        "category": category,
        "brand": brand,
        "content_hash": content_hash,
        "model_version": model_version,
        "aggregate_version": aggregate_version,
        "indexed_at": indexed_at.isoformat(),
    }


def pending_content_fields(
    *,
    name: str,
    description: str,
    category: str,
    brand: str,
    aggregate_version: int,
    indexed_at: datetime,
) -> dict[str, object]:
    """Контентные поля при постановке ре-эмбеддинга (фаза A, §9.4).

    Как ``content_payload``, но без ``content_hash``/``model_version`` —
    причина та же, что у ``pending_payload``.
    """
    fields = content_payload(
        name=name,
        description=description,
        category=category,
        brand=brand,
        content_hash="",
        model_version="",
        aggregate_version=aggregate_version,
        indexed_at=indexed_at,
    )
    del fields["content_hash"]
    del fields["model_version"]
    return fields


def commercial_payload(
    *,
    pricing: Pricing,
    stock: StockLevel,
    supplier: str,
    aggregate_version: int,
    indexed_at: datetime,
) -> dict[str, object]:
    """Частичный payload для set_payload без ре-эмбеддинга (§6.3)."""
    margin = pricing.calculate_margin()
    return {
        "price": float(pricing.price.amount),
        "cost": float(pricing.cost.amount),
        "currency": pricing.price.currency.code,
        "stock": stock.quantity,
        "in_stock": stock.is_in_stock,
        "supplier": supplier,
        "margin_percent": _opt_float(margin.percent),
        "aggregate_version": aggregate_version,
        "indexed_at": indexed_at.isoformat(),
    }


def tombstone_fields(
    *, aggregate_version: int, deleted_at: datetime
) -> dict[str, object]:
    """Частичный payload tombstone: помечает точку удалённой (§6.5)."""
    return {
        "is_deleted": True,
        "deleted_at": deleted_at.isoformat(),
        "aggregate_version": aggregate_version,
    }
