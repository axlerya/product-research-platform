"""Тесты сводок результатов инструментов для LLM."""

from decimal import Decimal

from research_agent_service.application.dto.price_analysis import (
    MarginBand,
    MarginStats,
    Outlier,
    PriceAnalysisResult,
    PriceStats,
)
from research_agent_service.application.dto.retrieval import (
    RagContext,
    RankedProduct,
)
from research_agent_service.application.dto.web import WebResult
from research_agent_service.domain.value_objects.currency import Currency
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.money import Money
from research_agent_service.infrastructure.agent.observations import (
    price_observation,
    rag_observation,
    web_observation,
)

_RUB = Currency("RUB")


def test_rag_observation_serializes_money_and_degradations() -> None:
    """Товары с ценой-Money и деградации попадают в сводку строками."""
    context = RagContext(
        products=(
            RankedProduct(
                sku="SKU-1",
                name="Наушники",
                category="Аудио",
                snippet="описание",
                price=Money.of(Decimal("99.90"), _RUB),
                in_stock=True,
                margin_percent=Decimal("25.5"),
                rerank_score=Decimal("0.9"),
                price_authoritative=True,
            ),
        ),
        citations=(),
        degradations=(Degradation("catalog", "unavailable"),),
    )

    observation = rag_observation(context)

    product = observation["products"][0]
    assert product["price"] == {"amount": "99.90", "currency": "RUB"}
    assert product["margin_percent"] == "25.5"
    assert product["price_authoritative"] is True
    assert observation["degraded"] == ["catalog"]


def test_rag_observation_handles_missing_price() -> None:
    """Товар без цены → price=None."""
    context = RagContext(
        products=(
            RankedProduct(
                sku="SKU-2",
                name="Кабель",
                category="Аксессуары",
                snippet="s",
            ),
        ),
        citations=(),
    )

    observation = rag_observation(context)

    assert observation["products"][0]["price"] is None
    assert observation["products"][0]["margin_percent"] is None
    assert observation["degraded"] == []


def _price_result() -> PriceAnalysisResult:
    return PriceAnalysisResult(
        count=3,
        currency=_RUB,
        price=PriceStats(
            min=Decimal("10"),
            max=Decimal("30"),
            avg=Decimal("20"),
            median=Decimal("20"),
            stddev=Decimal("8.16"),
        ),
        margin=MarginStats(
            min_percent=Decimal("5"),
            max_percent=Decimal("40"),
            avg_percent=Decimal("22"),
            median_percent=Decimal("20"),
            undefined_count=1,
            negative_count=0,
        ),
        analysis_ref="analysis-abc",
        bands=(
            MarginBand(label="низкая", count=2, upper_percent=Decimal("10")),
        ),
        outliers=(
            Outlier(
                sku="SKU-9",
                price=Money.of(Decimal("500"), _RUB),
                reason="too_high",
                score=Decimal("3.2"),
            ),
        ),
    )


def test_price_observation_maps_stats_bands_outliers() -> None:
    """Числа catalog переносятся строками; ref, бэнды и выбросы на месте."""
    observation = price_observation(_price_result())

    assert observation["count"] == 3
    assert observation["currency"] == "RUB"
    assert observation["analysis_ref"] == "analysis-abc"
    assert observation["price"]["median"] == "20"
    assert observation["margin"]["undefined_count"] == 1
    assert observation["bands"][0] == {
        "label": "низкая",
        "count": 2,
        "lower_percent": None,
        "upper_percent": "10",
    }
    assert observation["outliers"][0]["price"] == {
        "amount": "500.00",
        "currency": "RUB",
    }
    assert observation["outliers"][0]["score"] == "3.2"


def test_web_observation_lists_results() -> None:
    """Результаты web-поиска переносятся один-в-один."""
    observation = web_observation(
        (
            WebResult(
                title="Обзор",
                url="https://example.com/a",
                snippet="фрагмент",
                published_at="2026-01-01",
            ),
            WebResult(
                title="Без даты", url="https://example.com/b", snippet="s"
            ),
        )
    )

    assert observation["results"][0]["url"] == "https://example.com/a"
    assert observation["results"][0]["published_at"] == "2026-01-01"
    assert observation["results"][1]["published_at"] is None
