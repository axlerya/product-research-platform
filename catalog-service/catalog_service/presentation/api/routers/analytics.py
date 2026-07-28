"""Роутер аналитики маржинальности и ценового анализа срезов."""

from fastapi import APIRouter

from catalog_service.presentation.api.deps import (
    AnalyzePricesDep,
    ProductQueryDep,
)
from catalog_service.presentation.api.schemas.analytics import (
    PriceAnalysisRead,
    PriceAnalysisRequest,
)
from catalog_service.presentation.api.schemas.common import Problem
from catalog_service.presentation.api.schemas.reads import CategoryMarginRead

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/margin", response_model=list[CategoryMarginRead])
async def margin_by_category(
    qs: ProductQueryDep, include_deleted: bool = False
) -> list[CategoryMarginRead]:
    """Маржинальность по категориям (avg/min/max)."""
    return [
        CategoryMarginRead.model_validate(row)
        for row in await qs.margin_by_category(include_deleted=include_deleted)
    ]


@router.post(
    "/prices",
    response_model=PriceAnalysisRead,
    responses={409: {"model": Problem}, 422: {"model": Problem}},
)
async def analyze_prices(
    body: PriceAnalysisRequest, uc: AnalyzePricesDep
) -> PriceAnalysisRead:
    """Детерминированная статистика цен и маржи по срезу товаров."""
    result = await uc.execute(
        body.selector.to_selector(), bands=body.to_bands()
    )
    return PriceAnalysisRead.model_validate(result)
