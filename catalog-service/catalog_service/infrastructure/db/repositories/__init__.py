"""Реализации репозиториев поверх SQLAlchemy."""

from catalog_service.infrastructure.db.repositories.outbox import (
    SqlAlchemyOutboxRepository,
)
from catalog_service.infrastructure.db.repositories.product import (
    SqlAlchemyProductRepository,
)
from catalog_service.infrastructure.db.repositories.references import (
    SqlAlchemyBrandRepository,
    SqlAlchemyCategoryRepository,
    SqlAlchemySupplierRepository,
)

__all__ = [
    "SqlAlchemyBrandRepository",
    "SqlAlchemyCategoryRepository",
    "SqlAlchemyOutboxRepository",
    "SqlAlchemyProductRepository",
    "SqlAlchemySupplierRepository",
]
