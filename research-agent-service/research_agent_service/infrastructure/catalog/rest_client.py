"""HttpCatalogClient — REST-клиент к catalog-service (порт CatalogPort).

Транспорт — REST (эндпоинты by-skus / analytics/prices catalog-service).
Деньги/маржа приходят строками и разбираются в Decimal/Money; сетевые
ошибки транслируются в CatalogUnavailable (сигнал деградации).
"""

from collections.abc import Mapping
from decimal import Decimal

import httpx

from research_agent_service.application.dto.catalog import (
    CatalogFetch,
    CatalogProduct,
)
from research_agent_service.application.dto.price_analysis import (
    MarginBand,
    MarginBandSpec,
    MarginStats,
    Outlier,
    PriceAnalysisResult,
    PriceStats,
    ProductSelector,
)
from research_agent_service.application.exceptions import CatalogUnavailable
from research_agent_service.domain.value_objects.currency import Currency
from research_agent_service.domain.value_objects.money import Money


def _money(raw: Mapping[str, str]) -> Money:
    return Money.of(raw["amount"], Currency(raw["currency"]))


def _opt_decimal(raw: object) -> Decimal | None:
    return Decimal(str(raw)) if raw is not None else None


def _opt_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


class HttpCatalogClient:
    """Чтение авторитетных данных и ценового анализа из catalog по REST."""

    def __init__(self, *, client: httpx.AsyncClient) -> None:
        self._client = client

    async def get_products_by_skus(self, skus: tuple[str, ...]) -> CatalogFetch:
        """Batch-чтение товаров; сетевой сбой → CatalogUnavailable."""
        body = await self._post(
            "/api/v1/products/by-skus",
            {"skus": list(skus), "include_deleted": False},
        )
        products = tuple(self._product(item) for item in body["products"])
        missing = tuple(body.get("missing_skus", ()))
        return CatalogFetch(products=products, missing_skus=missing)

    async def analyze_prices(
        self,
        selector: ProductSelector,
        *,
        bands: tuple[MarginBandSpec, ...] = (),
    ) -> PriceAnalysisResult:
        """Детерминированный ценовой анализ (математика — в catalog)."""
        payload = {
            "selector": self._selector(selector),
            "bands": [self._band_spec(band) for band in bands],
        }
        body = await self._post("/api/v1/analytics/prices", payload)
        return self._analysis(body)

    async def _post(
        self, path: str, payload: Mapping[str, object]
    ) -> Mapping[str, object]:
        try:
            response = await self._client.post(path, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CatalogUnavailable(str(exc)) from exc
        return response.json()

    @staticmethod
    def _product(item: Mapping[str, object]) -> CatalogProduct:
        margin = item.get("margin") or {}
        return CatalogProduct(
            sku=str(item["sku"]),
            name=str(item["name"]),
            category=str(item["category"]),
            brand=str(item["brand"]),
            supplier=str(item["supplier"]),
            price=_money(item["price"]),  # type: ignore[arg-type]
            cost=_money(item["cost"]),  # type: ignore[arg-type]
            stock=int(item["stock"]),  # type: ignore[call-overload]
            is_in_stock=bool(item["is_in_stock"]),
            margin_percent=_opt_decimal(margin.get("percent")),
            sales_per_month=item.get("sales_per_month"),  # type: ignore[arg-type]
            avg_rating=_opt_decimal(item.get("avg_rating")),
            review_count=item.get("review_count"),  # type: ignore[arg-type]
        )

    @staticmethod
    def _analysis(body: Mapping[str, object]) -> PriceAnalysisResult:
        price = body["price"]
        margin = body["margin"]
        return PriceAnalysisResult(
            count=int(body["count"]),  # type: ignore[call-overload]
            currency=Currency(str(body["currency"])),
            price=PriceStats(
                min=Decimal(price["min"]),
                max=Decimal(price["max"]),
                avg=Decimal(price["avg"]),
                median=Decimal(price["median"]),
                stddev=Decimal(price["stddev"]),
            ),
            margin=MarginStats(
                min_percent=Decimal(margin["min_percent"]),
                max_percent=Decimal(margin["max_percent"]),
                avg_percent=Decimal(margin["avg_percent"]),
                median_percent=Decimal(margin["median_percent"]),
                undefined_count=int(margin["undefined_count"]),
                negative_count=int(margin["negative_count"]),
            ),
            analysis_ref=str(body.get("analysis_ref", "")),
            bands=tuple(
                MarginBand(
                    label=str(band["label"]),
                    count=int(band["count"]),
                    lower_percent=_opt_decimal(band.get("lower_percent")),
                    upper_percent=_opt_decimal(band.get("upper_percent")),
                )
                for band in body.get("bands", ())
            ),
            outliers=tuple(
                Outlier(
                    sku=str(item["sku"]),
                    price=_money(item["price"]),
                    reason=str(item["reason"]),
                    score=Decimal(item["score"]),
                )
                for item in body.get("outliers", ())
            ),
        )

    @staticmethod
    def _selector(selector: ProductSelector) -> Mapping[str, object]:
        return {
            "skus": list(selector.skus),
            "category": selector.category,
            "brand": selector.brand,
            "supplier": selector.supplier,
            "text": selector.text,
            "price_min": _opt_str(selector.price_min),
            "price_max": _opt_str(selector.price_max),
            "in_stock": selector.in_stock,
            "min_rating": _opt_str(selector.min_rating),
            "margin_min": _opt_str(selector.margin_min),
            "margin_max": _opt_str(selector.margin_max),
            "include_deleted": selector.include_deleted,
        }

    @staticmethod
    def _band_spec(band: MarginBandSpec) -> Mapping[str, object]:
        return {
            "label": band.label,
            "lower_percent": _opt_str(band.lower_percent),
            "upper_percent": _opt_str(band.upper_percent),
        }
