"""Прикладной сервис price_analysis (тонкая обёртка над catalog)."""

from research_agent_service.application.dto.price_analysis import (
    MarginBandSpec,
    PriceAnalysisResult,
    ProductSelector,
)
from research_agent_service.application.ports.catalog import CatalogPort


class PriceAnalysisService:
    """Инструмент price_analysis.

    Никакой ценовой математики на нашей стороне: медиану, бэнды и выбросы
    считает catalog (INV-1). Мы передаём селектор и возвращаем готовые числа.
    """

    def __init__(self, *, catalog: CatalogPort) -> None:
        self._catalog = catalog

    async def analyze(
        self,
        selector: ProductSelector,
        *,
        bands: tuple[MarginBandSpec, ...] = (),
    ) -> PriceAnalysisResult:
        """Возвращает детерминированный анализ цен из catalog."""
        return await self._catalog.analyze_prices(selector, bands=bands)
