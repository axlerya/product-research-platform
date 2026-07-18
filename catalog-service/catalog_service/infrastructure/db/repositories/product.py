"""Реализация ``ProductRepository`` поверх SQLAlchemy."""

from sqlalchemy import ColumnElement, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from catalog_service.application.exceptions import (
    ConcurrencyConflict,
    DuplicateSku,
)
from catalog_service.domain.entities.product import Product
from catalog_service.domain.value_objects.identifiers import ProductId
from catalog_service.domain.value_objects.sku import Sku
from catalog_service.infrastructure.db.mappers import ProductMapper
from catalog_service.infrastructure.db.models import ProductORM


class SqlAlchemyProductRepository:
    """Хранилище товара с оптимистичной блокировкой по ``version``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, product_id: ProductId) -> Product | None:
        return await self._get(ProductORM.id == product_id.value)

    async def get_by_sku(self, sku: Sku) -> Product | None:
        return await self._get(ProductORM.sku == sku.value)

    async def _get(self, where: ColumnElement[bool]) -> Product | None:
        stmt = (
            select(ProductORM)
            .where(where)
            .options(
                selectinload(ProductORM.category),
                selectinload(ProductORM.brand),
                selectinload(ProductORM.supplier),
            )
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return ProductMapper.to_domain(row) if row is not None else None

    async def add(self, product: Product) -> None:
        self._session.add(ProductMapper.to_orm(product))
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise DuplicateSku(
                f"Товар с артикулом {product.sku.value} уже существует",
                meta={"sku": product.sku.value},
            ) from exc

    async def update(self, product: Product, *, expected_version: int) -> None:
        stmt = (
            update(ProductORM)
            .where(
                ProductORM.id == product.id.value,
                ProductORM.version == expected_version,
            )
            .values(
                name=product.name,
                description=product.description,
                category_id=product.category.id.value,
                brand_id=product.brand.id.value,
                supplier_id=product.supplier.id.value,
                price_amount=product.pricing.price.amount,
                cost_amount=product.pricing.cost.amount,
                currency=product.pricing.price.currency.code,
                stock_quantity=product.stock.quantity,
                sales_per_month=product.metrics.sales_per_month,
                avg_rating=product.metrics.avg_rating.value,
                review_count=product.metrics.review_count,
                source_updated_at=product.source_updated_at,
                version=product.version,
                is_deleted=product.is_deleted,
                deleted_at=product.deleted_at,
                updated_at=product.updated_at,
            )
        )
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            raise ConcurrencyConflict(
                f"Товар {product.sku.value} изменён параллельно",
                meta={
                    "sku": product.sku.value,
                    "expected_version": expected_version,
                },
            )
