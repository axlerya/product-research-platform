"""Роутер аналитики маржинальности."""

from fastapi import APIRouter

from catalog_service.presentation.api.deps import ProductQueryDep
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
