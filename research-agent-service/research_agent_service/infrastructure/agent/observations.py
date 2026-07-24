"""Сводки результатов инструментов для LLM (компактный JSON-наблюдение).

Наблюдение — то, что модель видит после вызова инструмента. Decimal/Money
сериализуются в строки, чтобы не терять точность и не протаскивать float.
Provenance (sku/url/analysis_ref) сюда не относится — его собирает executor.
"""

from decimal import Decimal

from research_agent_service.application.dto.price_analysis import (
    PriceAnalysisResult,
)
from research_agent_service.application.dto.retrieval import RagContext
from research_agent_service.application.dto.web import WebResult
from research_agent_service.domain.value_objects.money import Money


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _money(value: Money | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {"amount": str(value.amount), "currency": value.currency.code}


def rag_observation(context: RagContext) -> dict[str, object]:
    """Товары и деградации retrieval-пайплайна для LLM."""
    return {
        "products": [
            {
                "sku": product.sku,
                "name": product.name,
                "category": product.category,
                "snippet": product.snippet,
                "price": _money(product.price),
                "in_stock": product.in_stock,
                "margin_percent": _decimal(product.margin_percent),
                "price_authoritative": product.price_authoritative,
            }
            for product in context.products
        ],
        "degraded": [d.dependency for d in context.degradations],
    }


def price_observation(result: PriceAnalysisResult) -> dict[str, object]:
    """Детерминированный ценовой анализ (числа из catalog) для LLM."""
    return {
        "count": result.count,
        "currency": result.currency.code,
        "analysis_ref": result.analysis_ref,
        "price": {
            "min": _decimal(result.price.min),
            "max": _decimal(result.price.max),
            "avg": _decimal(result.price.avg),
            "median": _decimal(result.price.median),
            "stddev": _decimal(result.price.stddev),
        },
        "margin": {
            "min_percent": _decimal(result.margin.min_percent),
            "max_percent": _decimal(result.margin.max_percent),
            "avg_percent": _decimal(result.margin.avg_percent),
            "median_percent": _decimal(result.margin.median_percent),
            "undefined_count": result.margin.undefined_count,
            "negative_count": result.margin.negative_count,
        },
        "bands": [
            {
                "label": band.label,
                "count": band.count,
                "lower_percent": _decimal(band.lower_percent),
                "upper_percent": _decimal(band.upper_percent),
            }
            for band in result.bands
        ],
        "outliers": [
            {
                "sku": outlier.sku,
                "price": _money(outlier.price),
                "reason": outlier.reason,
                "score": _decimal(outlier.score),
            }
            for outlier in result.outliers
        ],
    }


def web_observation(results: tuple[WebResult, ...]) -> dict[str, object]:
    """Обеззараженные результаты web-поиска для LLM."""
    return {
        "results": [
            {
                "title": result.title,
                "url": result.url,
                "snippet": result.snippet,
                "published_at": result.published_at,
            }
            for result in results
        ]
    }
