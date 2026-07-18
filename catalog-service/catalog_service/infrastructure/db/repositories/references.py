"""Реализации справочных репозиториев (идемпотентный get-or-create)."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from catalog_service.domain.entities.reference import (
    Brand,
    Category,
    Supplier,
)
from catalog_service.domain.value_objects.identifiers import (
    BrandId,
    CategoryId,
    SupplierId,
)
from catalog_service.infrastructure.db.models import (
    BrandORM,
    CategoryORM,
    SupplierORM,
)


class _SqlAlchemyReferenceRepository:
    """Общая реализация get-or-create через ``INSERT ... ON CONFLICT``."""

    _orm: type
    _entity: type
    _id: type

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, name: str):
        name = name.strip()
        insert_stmt = (
            pg_insert(self._orm)
            .values(id=self._id.new().value, name=name)
            .on_conflict_do_nothing(index_elements=["name"])
            .returning(self._orm.id, self._orm.created_at)
        )
        row = (await self._session.execute(insert_stmt)).first()
        if row is not None:
            return self._entity(
                id=self._id(row.id), name=name, created_at=row.created_at
            )
        existing = (
            await self._session.execute(
                select(self._orm).where(self._orm.name == name)
            )
        ).scalar_one()
        return self._entity(
            id=self._id(existing.id),
            name=existing.name,
            created_at=existing.created_at,
        )


class SqlAlchemyCategoryRepository(_SqlAlchemyReferenceRepository):
    """Справочник категорий."""

    _orm = CategoryORM
    _entity = Category
    _id = CategoryId


class SqlAlchemyBrandRepository(_SqlAlchemyReferenceRepository):
    """Справочник брендов."""

    _orm = BrandORM
    _entity = Brand
    _id = BrandId


class SqlAlchemySupplierRepository(_SqlAlchemyReferenceRepository):
    """Справочник поставщиков."""

    _orm = SupplierORM
    _entity = Supplier
    _id = SupplierId
