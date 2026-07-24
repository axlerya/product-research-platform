"""Тесты детерминированной статистики цен и маржи по срезу товаров."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from catalog_service.application.dto.queries import MarginBandSpec
from catalog_service.application.dto.views import (
    MarginView,
    MoneyView,
    ProductView,
)
from catalog_service.application.exceptions import MixedCurrencySlice
from catalog_service.application.price_analysis import analyze

_NOW = datetime(2026, 7, 24, tzinfo=UTC)
_PID = UUID("0192f0c8-7b3a-7e2d-9a1c-000000000001")


def _product(
    sku: str,
    price: str,
    cost: str = "50.00",
    *,
    currency: str = "RUB",
    margin: str | None = None,
) -> ProductView:
    """Товар среза: маржа задаётся явно (``None`` — не определена)."""
    price_value = Decimal(price)
    cost_value = Decimal(cost)
    percent = None if margin is None else Decimal(margin)
    return ProductView(
        id=_PID,
        sku=sku,
        name=f"Товар {sku}",
        description="Опис",
        category="Электроника",
        brand="AudioMax",
        supplier="TechSupply Co",
        price=MoneyView(price_value, currency),
        cost=MoneyView(cost_value, currency),
        stock=5,
        is_in_stock=True,
        sales_per_month=10,
        avg_rating=Decimal("4.50"),
        review_count=7,
        margin=MarginView(
            MoneyView(price_value - cost_value, currency), percent
        ),
        source_updated_at=None,
        version=1,
        is_deleted=False,
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_empty_slice_returns_zeros_and_fallback_currency():
    """Пустой срез не падает: нули, валюта по умолчанию, стабильный ref."""
    result = analyze((), default_currency="RUB")
    assert result.count == 0
    assert result.currency == "RUB"
    assert result.price.min == Decimal("0.00")
    assert result.price.median == Decimal("0.00")
    assert result.price.stddev == Decimal("0.00")
    assert result.margin.undefined_count == 0
    assert result.margin.negative_count == 0
    assert result.outliers == ()
    assert result.analysis_ref.startswith("pa-")


def test_price_stats_on_odd_count():
    """Нечётный срез: медиана — средний элемент, stddev выборочная."""
    products = (
        _product("PROD-1", "10.00", margin="50.00"),
        _product("PROD-3", "30.00", margin="50.00"),
        _product("PROD-2", "20.00", margin="50.00"),
    )
    result = analyze(products, default_currency="RUB")
    assert result.count == 3
    assert result.price.min == Decimal("10.00")
    assert result.price.max == Decimal("30.00")
    assert result.price.avg == Decimal("20.00")
    assert result.price.median == Decimal("20.00")
    assert result.price.stddev == Decimal("10.00")


def test_price_median_on_even_count_averages_middle_pair():
    """Чётный срез: медиана — среднее двух центральных значений."""
    products = tuple(
        _product(f"PROD-{i}", price, margin="50.00")
        for i, price in enumerate(("10.00", "20.00", "30.00", "40.00"))
    )
    assert analyze(products, default_currency="RUB").price.median == Decimal(
        "25.00"
    )


def test_single_product_has_zero_stddev():
    """Выборочное отклонение на одном наблюдении не определено — ноль."""
    result = analyze(
        (_product("PROD-1", "10.00", margin="50.00"),), default_currency="RUB"
    )
    assert result.price.stddev == Decimal("0.00")
    assert result.price.median == Decimal("10.00")


def test_margin_stats_count_undefined_and_negative():
    """Маржа: неопределённые не входят в статистику, но считаются."""
    products = (
        _product("PROD-1", "100.00", "50.00", margin="50.00"),
        _product("PROD-2", "100.00", "150.00", margin="-50.00"),
        _product("PROD-3", "0.00", "10.00", margin=None),
        _product("PROD-4", "100.00", "70.00", margin="30.00"),
    )
    result = analyze(products, default_currency="RUB")
    assert result.margin.undefined_count == 1
    assert result.margin.negative_count == 1
    assert result.margin.min_percent == Decimal("-50.00")
    assert result.margin.max_percent == Decimal("50.00")
    assert result.margin.avg_percent == Decimal("10.00")
    assert result.margin.median_percent == Decimal("30.00")


def test_all_margins_undefined_yields_zero_stats():
    """Срез без определённой маржи: статистика нулевая, счётчик полный."""
    products = (
        _product("PROD-1", "0.00", "10.00", margin=None),
        _product("PROD-2", "0.00", "20.00", margin=None),
    )
    result = analyze(products, default_currency="RUB")
    assert result.margin.undefined_count == 2
    assert result.margin.avg_percent == Decimal("0.00")
    assert result.margin.median_percent == Decimal("0.00")


def test_bands_are_half_open_intervals():
    """Бэнд включает нижнюю границу и исключает верхнюю."""
    products = (
        _product("PROD-1", "100.00", margin="10.00"),
        _product("PROD-2", "100.00", margin="20.00"),
        _product("PROD-3", "100.00", margin="30.00"),
        _product("PROD-4", "100.00", margin=None),
    )
    bands = (
        MarginBandSpec(label="низкая", upper_percent=Decimal("20")),
        MarginBandSpec(
            label="средняя",
            lower_percent=Decimal("20"),
            upper_percent=Decimal("30"),
        ),
        MarginBandSpec(label="высокая", lower_percent=Decimal("30")),
    )
    result = analyze(products, bands=bands, default_currency="RUB")
    assert [(band.label, band.count) for band in result.bands] == [
        ("низкая", 1),
        ("средняя", 1),
        ("высокая", 1),
    ]
    assert result.bands[0].lower_percent is None
    assert result.bands[0].upper_percent == Decimal("20")


def test_outlier_detected_by_modified_z_score():
    """Выброс ловится по MAD-скору (устойчив на малых выборках)."""
    products = (
        _product("PROD-1", "10.00", margin="50.00"),
        _product("PROD-2", "11.00", margin="50.00"),
        _product("PROD-3", "12.00", margin="50.00"),
        _product("PROD-4", "13.00", margin="50.00"),
        _product("PROD-5", "100.00", margin="50.00"),
    )
    result = analyze(products, default_currency="RUB")
    assert [outlier.sku for outlier in result.outliers] == ["PROD-5"]
    outlier = result.outliers[0]
    assert outlier.reason == "above_median"
    assert outlier.price == MoneyView(Decimal("100.00"), "RUB")
    assert outlier.score > Decimal("3.5")


def test_outlier_falls_back_to_mean_deviation_when_mad_is_zero():
    """Нулевой MAD (совпадающие цены) не прячет очевидный выброс."""
    products = (
        *(_product(f"PROD-{i}", "10.00", margin="50.00") for i in range(1, 5)),
        _product("PROD-5", "50.00", margin="50.00"),
    )
    result = analyze(products, default_currency="RUB")
    assert [outlier.sku for outlier in result.outliers] == ["PROD-5"]


def test_identical_prices_have_no_outliers():
    """Полностью однородный срез выбросов не содержит."""
    products = tuple(
        _product(f"PROD-{i}", "10.00", margin="50.00") for i in range(1, 4)
    )
    assert analyze(products, default_currency="RUB").outliers == ()


def test_outliers_sorted_by_score_desc_then_sku():
    """Порядок выбросов детерминирован: скор по убыванию, затем артикул."""
    products = (
        *(
            _product(f"PROD-{price}", f"{price}.00", margin="50.00")
            for price in range(10, 17)
        ),
        _product("PROD-9", "90.00", margin="50.00"),
        _product("PROD-8", "90.00", margin="50.00"),
        _product("PROD-A", "200.00", margin="50.00"),
    )
    skus = [outlier.sku for outlier in analyze(products).outliers]
    assert skus == ["PROD-A", "PROD-8", "PROD-9"]


def test_analysis_ref_is_stable_for_same_data():
    """Один и тот же срез даёт один и тот же provenance-идентификатор."""
    products = (
        _product("PROD-2", "20.00", margin="50.00"),
        _product("PROD-1", "10.00", margin="50.00"),
    )
    reordered = tuple(reversed(products))
    assert analyze(products).analysis_ref == analyze(reordered).analysis_ref


def test_analysis_ref_changes_when_data_changes():
    """Изменение цены меняет идентификатор среза (цитата не «залипает»)."""
    before = analyze((_product("PROD-1", "10.00", margin="50.00"),))
    after = analyze((_product("PROD-1", "11.00", margin="50.00"),))
    assert before.analysis_ref != after.analysis_ref


def test_currency_taken_from_slice():
    """Валюта результата берётся из товаров среза, а не из умолчания."""
    products = (_product("PROD-1", "10.00", currency="USD", margin="50.00"),)
    assert analyze(products, default_currency="RUB").currency == "USD"


def test_mixed_currency_slice_rejected():
    """Смешанные валюты — вне контракта: статистика была бы бессмысленной."""
    products = (
        _product("PROD-1", "10.00", currency="RUB", margin="50.00"),
        _product("PROD-2", "10.00", currency="USD", margin="50.00"),
    )
    with pytest.raises(MixedCurrencySlice):
        analyze(products)
