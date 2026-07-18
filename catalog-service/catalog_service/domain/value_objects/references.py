"""Reference-VO: снимок ссылки (id + name) внутри товара.

Имя — снимок на момент присвоения; единственный источник истины имени
остаётся в справочной сущности.
"""

from dataclasses import dataclass

from catalog_service.domain.value_objects.identifiers import (
    BrandId,
    CategoryId,
    SupplierId,
)


@dataclass(frozen=True, slots=True)
class CategoryRef:
    """Снимок ссылки на категорию (id + имя)."""

    id: CategoryId
    name: str


@dataclass(frozen=True, slots=True)
class BrandRef:
    """Снимок ссылки на бренд (id + имя)."""

    id: BrandId
    name: str


@dataclass(frozen=True, slots=True)
class SupplierRef:
    """Снимок ссылки на поставщика (id + имя)."""

    id: SupplierId
    name: str
