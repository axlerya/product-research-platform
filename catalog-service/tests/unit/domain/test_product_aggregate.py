"""Тесты агрегата ``Product`` — классификация изменений в события.

Проверяют канон: агрегат сам решает, какое поле → какое событие;
ровно один bump версии на команду с фактическим изменением; мутаторы
идемпотентны (no-op при value-equality); метрики бампают версию без
события; удаление — soft и идемпотентно.
"""

from decimal import Decimal

from catalog_service.domain.entities.product import Product
from catalog_service.domain.events import (
    ProductCommercialDataChanged,
    ProductContentChanged,
    ProductCreated,
    ProductDeleted,
)
from catalog_service.domain.value_objects.sku import Sku
from catalog_service.domain.value_objects.stock import StockLevel
from tests.support.factories import (
    FIXED_NOW,
    PRODUCT_ID,
    make_brand_ref,
    make_category_ref,
    make_metrics,
    make_pricing,
    make_product,
    make_supplier_ref,
)


def _create() -> Product:
    return Product.create(
        id=PRODUCT_ID,
        sku=Sku("PROD-001"),
        name="Наушники",
        description="Описание",
        category=make_category_ref(),
        brand=make_brand_ref(),
        supplier=make_supplier_ref(),
        pricing=make_pricing(),
        stock=StockLevel(245),
        metrics=make_metrics(),
        source_updated_at=None,
        now=FIXED_NOW,
    )


def test_create_emits_single_created_event():
    product = _create()
    assert product.version == 1
    events = product.collect_events()
    assert len(events) == 1
    assert isinstance(events[0], ProductCreated)
    assert events[0].routing_key == "catalog.product.created"


def test_collect_events_drains():
    product = _create()
    product.collect_events()
    assert product.collect_events() == []


def test_change_content_emits_event_and_bumps_version():
    product = make_product(version=1)
    product.change_content(name="Новое имя", now=FIXED_NOW)
    assert product.version == 2
    events = product.collect_events()
    assert len(events) == 1
    assert isinstance(events[0], ProductContentChanged)
    assert events[0].changed_fields == ("name",)


def test_change_content_no_diff_is_noop():
    product = make_product(name="Наушники", version=1)
    product.change_content(name="Наушники", now=FIXED_NOW)
    assert product.version == 1
    assert product.collect_events() == []


def test_change_commercial_price_and_stock():
    product = make_product(version=1)
    new_pricing = make_pricing(price="119.99", cost="65.00")
    product.change_commercial(
        pricing=new_pricing,
        stock=StockLevel(230),
        now=FIXED_NOW,
    )
    assert product.version == 2
    events = product.collect_events()
    assert len(events) == 1
    assert isinstance(events[0], ProductCommercialDataChanged)
    assert events[0].changed_fields == ("price", "stock")


def test_supplier_change_is_commercial():
    product = make_product(version=1)
    product.change_commercial(
        supplier=make_supplier_ref("НовыйПоставщик"),
        now=FIXED_NOW,
    )
    events = product.collect_events()
    assert events[0].changed_fields == ("supplier",)


def test_single_command_multi_event_shares_one_bump():
    product = make_product(version=4)
    product.change_content(name="Имя2", now=FIXED_NOW)
    product.change_commercial(
        pricing=make_pricing(price="99.99", cost="65.00"),
        now=FIXED_NOW,
    )
    assert product.version == 5  # ровно один bump на команду
    events = product.collect_events()
    assert len(events) == 2
    assert {type(e) for e in events} == {
        ProductContentChanged,
        ProductCommercialDataChanged,
    }


def test_update_metrics_bumps_version_without_event():
    product = make_product(version=1)
    product.update_metrics(make_metrics(sales=999), now=FIXED_NOW)
    assert product.version == 2
    assert product.collect_events() == []


def test_update_metrics_no_diff_is_noop():
    product = make_product(metrics=make_metrics(), version=1)
    product.update_metrics(make_metrics(), now=FIXED_NOW)
    assert product.version == 1
    assert product.collect_events() == []


def test_delete_emits_event_and_soft_deletes():
    product = make_product(version=1)
    product.delete(now=FIXED_NOW)
    assert product.is_deleted is True
    assert product.deleted_at == FIXED_NOW
    assert product.version == 2
    events = product.collect_events()
    assert isinstance(events[0], ProductDeleted)


def test_delete_is_idempotent():
    product = make_product(version=1, is_deleted=True)
    product.delete(now=FIXED_NOW)
    assert product.version == 1
    assert product.collect_events() == []


def test_margin_delegates_to_pricing():
    product = make_product(pricing=make_pricing("129.99", "65.00"))
    assert product.margin().percent == Decimal("50.00")


def test_change_content_description_category_brand():
    product = make_product(version=1)
    product.change_content(
        description="Новое описание",
        category=make_category_ref("Гаджеты"),
        brand=make_brand_ref("SoundPro"),
        now=FIXED_NOW,
    )
    assert product.version == 2
    events = product.collect_events()
    assert events[0].changed_fields == (
        "description",
        "category",
        "brand",
    )


def test_change_commercial_cost_only():
    product = make_product(pricing=make_pricing("129.99", "65.00"), version=1)
    product.change_commercial(
        pricing=make_pricing("129.99", "70.00"), now=FIXED_NOW
    )
    events = product.collect_events()
    assert events[0].changed_fields == ("cost",)


def test_change_commercial_no_diff_is_noop():
    product = make_product(pricing=make_pricing("129.99", "65.00"), version=1)
    product.change_commercial(
        pricing=make_pricing("129.99", "65.00"), now=FIXED_NOW
    )
    assert product.version == 1
    assert product.collect_events() == []
