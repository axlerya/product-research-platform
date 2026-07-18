"""Тесты справочных сущностей ``Category`` / ``Brand`` / ``Supplier``."""

from uuid import UUID

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
from tests.support.factories import FIXED_NOW


def test_category_holds_identity_and_name():
    category = Category(
        id=CategoryId(UUID(int=1)),
        name="Электроника",
        created_at=FIXED_NOW,
    )
    assert category.name == "Электроника"
    assert category.id == CategoryId(UUID(int=1))


def test_brand_and_supplier_construct():
    brand = Brand(
        id=BrandId(UUID(int=2)), name="AudioMax", created_at=FIXED_NOW
    )
    supplier = Supplier(
        id=SupplierId(UUID(int=3)),
        name="TechSupply Co",
        created_at=FIXED_NOW,
    )
    assert brand.name == "AudioMax"
    assert supplier.name == "TechSupply Co"
