"""Тесты PriceAnalysisService — делегирование ценового анализа в catalog."""

from decimal import Decimal

from research_agent_service.application.dto.price_analysis import (
    MarginBandSpec,
    MarginStats,
    PriceAnalysisResult,
    PriceStats,
    ProductSelector,
)
from research_agent_service.application.services.price_analysis import (
    PriceAnalysisService,
)
from research_agent_service.domain.value_objects.currency import Currency


def _result() -> PriceAnalysisResult:
    """Готовый результат анализа (как его вернул бы catalog)."""
    return PriceAnalysisResult(
        count=42,
        currency=Currency("RUB"),
        price=PriceStats(
            min=Decimal("100.00"),
            max=Decimal("5000.00"),
            avg=Decimal("1200.00"),
            median=Decimal("900.00"),
            stddev=Decimal("300.00"),
        ),
        margin=MarginStats(
            min_percent=Decimal("5.00"),
            max_percent=Decimal("40.00"),
            avg_percent=Decimal("22.00"),
            median_percent=Decimal("20.00"),
            undefined_count=1,
            negative_count=0,
        ),
        analysis_ref="slice-abc",
    )


class _FakeCatalog:
    """Catalog-порт, возвращающий заранее заданный результат."""

    def __init__(self, result: PriceAnalysisResult) -> None:
        self._result = result
        self.selector: ProductSelector | None = None
        self.bands: tuple[MarginBandSpec, ...] | None = None

    async def analyze_prices(
        self,
        selector: ProductSelector,
        *,
        bands: tuple[MarginBandSpec, ...] = (),
    ) -> PriceAnalysisResult:
        self.selector = selector
        self.bands = bands
        return self._result


async def test_analyze_delegates_to_catalog() -> None:
    """Результат catalog возвращается без изменений (никакой математики)."""
    result = _result()
    service = PriceAnalysisService(catalog=_FakeCatalog(result))

    got = await service.analyze(ProductSelector(category="Наушники"))

    assert got is result
    assert got.count == 42
    assert got.analysis_ref == "slice-abc"


async def test_analyze_forwards_selector_and_bands() -> None:
    """Селектор и границы бэндов передаются в catalog без изменений."""
    fake = _FakeCatalog(_result())
    service = PriceAnalysisService(catalog=fake)
    selector = ProductSelector(skus=("SKU-1",))
    bands = (
        MarginBandSpec(
            label="0-10%",
            lower_percent=Decimal("0"),
            upper_percent=Decimal("10"),
        ),
    )

    await service.analyze(selector, bands=bands)

    assert fake.selector is selector
    assert fake.bands == bands
