"""Порт CatalogPort — чтение из catalog-service (актуальные данные и анализ).

Транспорт (REST/gRPC) — деталь адаптера; порт остаётся неизменным.
"""

from typing import Protocol

from research_agent_service.application.dto.price_analysis import (
    MarginBandSpec,
    PriceAnalysisResult,
    ProductSelector,
)


class CatalogPort(Protocol):
    """Доступ к catalog-service для актуальных данных и ценового анализа."""

    async def analyze_prices(
        self,
        selector: ProductSelector,
        *,
        bands: tuple[MarginBandSpec, ...] = (),
    ) -> PriceAnalysisResult:
        """Детерминированный ценовой анализ (вся математика — в catalog)."""
        ...
