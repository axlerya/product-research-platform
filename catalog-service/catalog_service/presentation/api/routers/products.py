"""Роутер товаров — write-эндпоинты (команды)."""

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Path, Response

from catalog_service.application.dto.commands import (
    CreateProductCommand,
    DeleteProductCommand,
    SetStockCommand,
    UpdateCommercialDataCommand,
    UpdateMetricsCommand,
    UpdateProductContentCommand,
)
from catalog_service.presentation.api.deps import (
    CreateProductDep,
    DeleteProductDep,
    SetStockDep,
    UpdateCommercialDep,
    UpdateContentDep,
    UpdateMetricsDep,
)
from catalog_service.presentation.api.schemas.common import (
    Problem,
    WriteResult,
)
from catalog_service.presentation.api.schemas.products import (
    MetricsUpdate,
    ProductCommercialUpdate,
    ProductContentUpdate,
    ProductCreate,
    StockUpdate,
)

router = APIRouter(prefix="/api/v1/products", tags=["products"])

_ERRORS = {
    404: {"model": Problem},
    409: {"model": Problem},
    422: {"model": Problem},
    428: {"model": Problem},
}
ProductIdPath = Annotated[UUID, Path()]
IfMatch = Annotated[str | None, Header(alias="If-Match")]


def _expected_version(if_match: str | None) -> int:
    if if_match is None:
        raise HTTPException(
            status_code=428, detail="Требуется заголовок If-Match"
        )
    match = re.fullmatch(r'(?:W/)?"(\d+)"', if_match.strip())
    if match is None:
        raise HTTPException(status_code=400, detail="Некорректный If-Match")
    return int(match.group(1))


def _write_result(response: Response, result) -> WriteResult:
    response.headers["ETag"] = f'"{result.version}"'
    return WriteResult(
        id=result.product_id, sku=result.sku, version=result.version
    )


@router.post("", status_code=201, response_model=WriteResult, responses=_ERRORS)
async def create_product(
    body: ProductCreate, uc: CreateProductDep, response: Response
) -> WriteResult:
    """Создаёт товар."""
    result = await uc.execute(
        CreateProductCommand(
            sku=body.sku,
            name=body.name,
            description=body.description,
            category_name=body.category,
            brand_name=body.brand,
            supplier_name=body.supplier,
            price_amount=body.price,
            cost_amount=body.cost,
            stock_quantity=body.stock,
            sales_per_month=body.sales_per_month,
            avg_rating=body.avg_rating,
            review_count=body.review_count,
            source_updated_at=body.source_updated_at,
        )
    )
    response.headers["Location"] = f"/api/v1/products/{result.product_id}"
    return _write_result(response, result)


@router.patch("/{product_id}", response_model=WriteResult, responses=_ERRORS)
async def update_content(
    product_id: ProductIdPath,
    body: ProductContentUpdate,
    uc: UpdateContentDep,
    response: Response,
    if_match: IfMatch = None,
) -> WriteResult:
    """Меняет контентные поля товара."""
    result = await uc.execute(
        UpdateProductContentCommand(
            product_id=product_id,
            expected_version=_expected_version(if_match),
            name=body.name,
            description=body.description,
            category_name=body.category,
            brand_name=body.brand,
        )
    )
    return _write_result(response, result)


@router.patch(
    "/{product_id}/commercial",
    response_model=WriteResult,
    responses=_ERRORS,
)
async def update_commercial(
    product_id: ProductIdPath,
    body: ProductCommercialUpdate,
    uc: UpdateCommercialDep,
    response: Response,
    if_match: IfMatch = None,
) -> WriteResult:
    """Меняет коммерческие данные (цена/себестоимость/поставщик)."""
    result = await uc.execute(
        UpdateCommercialDataCommand(
            product_id=product_id,
            expected_version=_expected_version(if_match),
            price_amount=body.price,
            cost_amount=body.cost,
            supplier_name=body.supplier,
        )
    )
    return _write_result(response, result)


@router.patch(
    "/{product_id}/stock", response_model=WriteResult, responses=_ERRORS
)
async def set_stock(
    product_id: ProductIdPath,
    body: StockUpdate,
    uc: SetStockDep,
    response: Response,
    if_match: IfMatch = None,
) -> WriteResult:
    """Устанавливает абсолютное значение остатка."""
    result = await uc.execute(
        SetStockCommand(
            product_id=product_id,
            expected_version=_expected_version(if_match),
            stock_quantity=body.stock,
        )
    )
    return _write_result(response, result)


@router.patch(
    "/{product_id}/metrics", response_model=WriteResult, responses=_ERRORS
)
async def update_metrics(
    product_id: ProductIdPath,
    body: MetricsUpdate,
    uc: UpdateMetricsDep,
    response: Response,
    if_match: IfMatch = None,
) -> WriteResult:
    """Заменяет метрики товара (без события)."""
    result = await uc.execute(
        UpdateMetricsCommand(
            product_id=product_id,
            expected_version=_expected_version(if_match),
            sales_per_month=body.sales_per_month,
            avg_rating=body.avg_rating,
            review_count=body.review_count,
        )
    )
    return _write_result(response, result)


@router.delete("/{product_id}", status_code=204, responses=_ERRORS)
async def delete_product(
    product_id: ProductIdPath,
    uc: DeleteProductDep,
    if_match: IfMatch = None,
) -> None:
    """Мягко удаляет товар."""
    await uc.execute(
        DeleteProductCommand(
            product_id=product_id,
            expected_version=_expected_version(if_match),
        )
    )
