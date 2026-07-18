"""Тесты reference-VO (снимок ссылки id+name внутри товара)."""

from uuid import UUID

from catalog_service.domain.value_objects.identifiers import CategoryId
from catalog_service.domain.value_objects.references import CategoryRef


def test_holds_id_and_name():
    ref = CategoryRef(CategoryId(UUID(int=1)), "Электроника")
    assert ref.name == "Электроника"
    assert ref.id == CategoryId(UUID(int=1))


def test_equality_by_value():
    first = CategoryRef(CategoryId(UUID(int=1)), "X")
    second = CategoryRef(CategoryId(UUID(int=1)), "X")
    assert first == second
