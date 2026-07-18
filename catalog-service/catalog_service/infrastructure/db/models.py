"""ORM-модели SQLAlchemy 2.0 — персистентные строки таблиц.

Это НЕ доменные сущности: анемичные модели-таблицы. Домен о них не знает;
связь — через ручной Data Mapper (см. ``mappers.py``). Производная колонка
``margin_percent`` (GENERATED) и trgm/partial-индексы задаются вручную в
миграции Alembic, а не здесь.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from catalog_service.infrastructure.db.base import (
    Base,
    money_amount,
    ts_tz,
    uuid_pk,
)


class CategoryORM(Base):
    """Таблица категорий."""

    __tablename__ = "categories"

    id: Mapped[uuid_pk]
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_at: Mapped[ts_tz] = mapped_column(server_default=func.now())


class BrandORM(Base):
    """Таблица брендов."""

    __tablename__ = "brands"

    id: Mapped[uuid_pk]
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_at: Mapped[ts_tz] = mapped_column(server_default=func.now())


class SupplierORM(Base):
    """Таблица поставщиков."""

    __tablename__ = "suppliers"

    id: Mapped[uuid_pk]
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_at: Mapped[ts_tz] = mapped_column(server_default=func.now())


class ProductORM(Base):
    """Таблица товаров (агрегат ``Product``)."""

    __tablename__ = "products"

    id: Mapped[uuid_pk]
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=""
    )

    category_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("categories.id"), nullable=False
    )
    brand_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("brands.id"), nullable=False
    )
    supplier_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False
    )

    price_amount: Mapped[money_amount] = mapped_column(nullable=False)
    cost_amount: Mapped[money_amount] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    sales_per_month: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    avg_rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, server_default="0"
    )
    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    source_updated_at: Mapped[date | None] = mapped_column(nullable=True)

    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    is_deleted: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )
    created_at: Mapped[ts_tz] = mapped_column(server_default=func.now())
    updated_at: Mapped[ts_tz] = mapped_column()
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Гидрация имён справочников (Data Mapper); eager-load через selectinload.
    category: Mapped[CategoryORM] = relationship(lazy="raise")
    brand: Mapped[BrandORM] = relationship(lazy="raise")
    supplier: Mapped[SupplierORM] = relationship(lazy="raise")

    __table_args__ = (
        CheckConstraint("price_amount >= 0", name="price_non_negative"),
        CheckConstraint("cost_amount >= 0", name="cost_non_negative"),
        CheckConstraint("stock_quantity >= 0", name="stock_non_negative"),
        CheckConstraint("sales_per_month >= 0", name="sales_non_negative"),
        CheckConstraint("review_count >= 0", name="review_count_non_negative"),
        CheckConstraint(
            "avg_rating >= 0 AND avg_rating <= 5", name="rating_range"
        ),
        CheckConstraint("char_length(currency) = 3", name="currency_len"),
        # uq_products_sku (SKU уникален включая soft-deleted) и индексы —
        # в миграции Alembic (см. следующий срез инфраструктуры).
    )


class OutboxORM(Base):
    """Таблица transactional outbox."""

    __tablename__ = "outbox"

    id: Mapped[uuid_pk]
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    headers: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    occurred_at: Mapped[ts_tz] = mapped_column()
    created_at: Mapped[ts_tz] = mapped_column(server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
