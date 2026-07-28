"""Детерминированный ценовой анализ среза товаров (read-side).

Вся арифметика — на ``Decimal``, без плавающей точки: результат обязан быть
воспроизводимым, потому что на него ссылается цитата потребителя
(``analysis_ref`` как provenance). Выбросы ищутся модифицированным z-скором
по медиане и MAD (Iglewicz–Hoaglin): в отличие от классического z, он не
разваливается на коротких срезах и не маскируется самим выбросом.
"""

import hashlib
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from catalog_service.application.dto.queries import (
    MarginBandSpec,
    PriceAnalysisSelector,
)
from catalog_service.application.dto.views import (
    MarginBandView,
    MarginStatsView,
    MoneyView,
    PriceAnalysisView,
    PriceOutlierView,
    PriceStatsView,
    ProductView,
)
from catalog_service.application.exceptions import MixedCurrencySlice
from catalog_service.application.ports.read_models import ProductQueryService

_QUANT = Decimal("0.01")
_ZERO = Decimal("0.00")
# Константы Iglewicz–Hoaglin: 0.6745 — MAD-оценка сигмы, 1.253314 — та же
# оценка через среднее абсолютное отклонение (запасной путь при MAD == 0).
_MAD_SCALE = Decimal("0.6745")
_MEAN_AD_SCALE = Decimal("1.253314")
_OUTLIER_THRESHOLD = Decimal("3.5")
_REF_PREFIX = "pa-"
_REF_LENGTH = 16


def _round(value: Decimal) -> Decimal:
    """Округляет до сотых (единая точность ответа)."""
    return value.quantize(_QUANT, rounding=ROUND_HALF_UP)


def _median(sorted_values: Sequence[Decimal]) -> Decimal:
    """Медиана уже отсортированной последовательности."""
    count = len(sorted_values)
    middle = count // 2
    if count % 2 == 1:
        return sorted_values[middle]
    return (sorted_values[middle - 1] + sorted_values[middle]) / 2


def _mean(values: Sequence[Decimal]) -> Decimal:
    """Среднее арифметическое непустой последовательности."""
    return sum(values, _ZERO) / len(values)


def _stddev(values: Sequence[Decimal]) -> Decimal:
    """Выборочное стандартное отклонение (на одном наблюдении — ноль)."""
    if len(values) < 2:
        return _ZERO
    mean = _mean(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return variance.sqrt()


def _price_stats(prices: Sequence[Decimal]) -> PriceStatsView:
    """Статистика цен по отсортированному списку."""
    if not prices:
        return PriceStatsView(
            min=_ZERO, max=_ZERO, avg=_ZERO, median=_ZERO, stddev=_ZERO
        )
    return PriceStatsView(
        min=_round(prices[0]),
        max=_round(prices[-1]),
        avg=_round(_mean(prices)),
        median=_round(_median(prices)),
        stddev=_round(_stddev(prices)),
    )


def _margin_stats(
    percents: Sequence[Decimal], *, undefined: int
) -> MarginStatsView:
    """Статистика маржи по отсортированным определённым процентам."""
    negative = sum(1 for percent in percents if percent < 0)
    if not percents:
        return MarginStatsView(
            min_percent=_ZERO,
            max_percent=_ZERO,
            avg_percent=_ZERO,
            median_percent=_ZERO,
            undefined_count=undefined,
            negative_count=negative,
        )
    return MarginStatsView(
        min_percent=_round(percents[0]),
        max_percent=_round(percents[-1]),
        avg_percent=_round(_mean(percents)),
        median_percent=_round(_median(percents)),
        undefined_count=undefined,
        negative_count=negative,
    )


def _in_band(percent: Decimal, band: MarginBandSpec) -> bool:
    """Попадает ли маржа в полуинтервал ``[lower, upper)``."""
    if band.lower_percent is not None and percent < band.lower_percent:
        return False
    return band.upper_percent is None or percent < band.upper_percent


def _bands(
    percents: Sequence[Decimal], specs: Sequence[MarginBandSpec]
) -> tuple[MarginBandView, ...]:
    """Раскладывает определённые маржи по заданным бэндам."""
    return tuple(
        MarginBandView(
            label=spec.label,
            count=sum(1 for percent in percents if _in_band(percent, spec)),
            lower_percent=spec.lower_percent,
            upper_percent=spec.upper_percent,
        )
        for spec in specs
    )


def _deviation_scale(
    deviations: Sequence[Decimal], sorted_deviations: Sequence[Decimal]
) -> Decimal:
    """Масштаб отклонения: MAD, иначе среднее абсолютное отклонение."""
    mad = _median(sorted_deviations)
    if mad > 0:
        return mad / _MAD_SCALE
    mean_ad = _mean(deviations)
    return mean_ad * _MEAN_AD_SCALE if mean_ad > 0 else _ZERO


def _outliers(
    products: Sequence[ProductView], median: Decimal, currency: str
) -> tuple[PriceOutlierView, ...]:
    """Ценовые выбросы среза по модифицированному z-скору."""
    deviations = [abs(product.price.amount - median) for product in products]
    scale = _deviation_scale(deviations, sorted(deviations))
    if scale <= 0:
        return ()
    found: list[PriceOutlierView] = []
    for product, deviation in zip(products, deviations, strict=True):
        score = _round(deviation / scale)
        if score < _OUTLIER_THRESHOLD:
            continue
        found.append(
            PriceOutlierView(
                sku=product.sku,
                price=MoneyView(_round(product.price.amount), currency),
                reason=(
                    "above_median"
                    if product.price.amount > median
                    else "below_median"
                ),
                score=score,
            )
        )
    return tuple(sorted(found, key=lambda item: (-item.score, item.sku)))


def _currency(products: Sequence[ProductView], fallback: str) -> str:
    """Единая валюта среза; смешанный срез — вне контракта."""
    currencies = {product.price.currency for product in products}
    if len(currencies) > 1:
        raise MixedCurrencySlice(
            "Срез содержит несколько валют: " + ", ".join(sorted(currencies)),
            meta={"currencies": sorted(currencies)},
        )
    return currencies.pop() if currencies else fallback


def _analysis_ref(products: Sequence[ProductView], currency: str) -> str:
    """Идентификатор среза: детерминирован по данным, а не по порядку."""
    rows = sorted(
        f"{product.sku}|{product.price.amount:.2f}|{product.cost.amount:.2f}"
        for product in products
    )
    digest = hashlib.sha256("\n".join([currency, *rows]).encode()).hexdigest()
    return f"{_REF_PREFIX}{digest[:_REF_LENGTH]}"


def analyze(
    products: Sequence[ProductView],
    *,
    bands: Sequence[MarginBandSpec] = (),
    default_currency: str = "RUB",
) -> PriceAnalysisView:
    """Считает статистику цен и маржи по срезу товаров.

    Args:
        products: Товары среза (порядок не влияет на результат).
        bands: Бэнды маржи для распределения (могут пересекаться).
        default_currency: Валюта ответа для пустого среза.

    Returns:
        Готовый ``PriceAnalysisView`` с детерминированным ``analysis_ref``.

    Raises:
        MixedCurrencySlice: В срезе больше одной валюты.
    """
    currency = _currency(products, default_currency)
    prices = sorted(product.price.amount for product in products)
    defined = sorted(
        product.margin.percent
        for product in products
        if product.margin.percent is not None
    )
    undefined = len(products) - len(defined)
    return PriceAnalysisView(
        count=len(products),
        currency=currency,
        price=_price_stats(prices),
        margin=_margin_stats(defined, undefined=undefined),
        analysis_ref=_analysis_ref(products, currency),
        bands=_bands(defined, bands),
        outliers=(
            _outliers(products, _median(prices), currency) if prices else ()
        ),
    )


class AnalyzePrices:
    """Ценовой анализ среза: отбор товаров read-моделью плюс статистика."""

    def __init__(
        self, *, products: ProductQueryService, default_currency: str
    ) -> None:
        self._products = products
        self._default_currency = default_currency

    async def execute(
        self,
        selector: PriceAnalysisSelector,
        *,
        bands: Sequence[MarginBandSpec] = (),
    ) -> PriceAnalysisView:
        """Отбирает товары по селектору и считает по ним статистику."""
        products = await self._products.select_for_analysis(selector)
        return analyze(
            products,
            bands=bands,
            default_currency=self._default_currency,
        )
