"""Роутер товаров — read-эндпоинты (запросы)."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query

from catalog_service.application.dto.queries import ProductSearchQuery
from catalog_service.application.exceptions import ProductNotFound
from catalog_service.presentation.api.deps import ProductQueryDep
from catalog_service.presentation.api.schemas.common import Problem
from catalog_service.presentation.api.schemas.reads import (
    MarginRead,
    Page,
    ProductBatchRead,
    ProductRead,
    ProductsBySkusRequest,
)

router = APIRouter(prefix="/api/v1/products", tags=["products"])
_NOT_FOUND = {404: {"model": Problem}}
ProductIdPath = Annotated[UUID, Path()]


@router.get("", response_model=Page[ProductRead])
async def search_products(
    qs: ProductQueryDep,
    q: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    supplier: str | None = None,
    price_min: Decimal | None = None,
    price_max: Decimal | None = None,
    in_stock: bool | None = None,
    min_rating: Decimal | None = None,
    margin_min: Decimal | None = None,
    margin_max: Decimal | None = None,
    include_deleted: bool = False,
    sort: str = "-created_at",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ProductRead]:
    """Ищет товары по фильтрам с пагинацией."""
    page = await qs.search(
        ProductSearchQuery(
            text=q,
            category=category,
            brand=brand,
            supplier=supplier,
            price_min=price_min,
            price_max=price_max,
            in_stock=in_stock,
            min_rating=min_rating,
            margin_min=margin_min,
            margin_max=margin_max,
            include_deleted=include_deleted,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    )
    return Page[ProductRead](
        items=[ProductRead.model_validate(view) for view in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("/by-skus", response_model=ProductBatchRead)
async def get_products_by_skus(
    body: ProductsBySkusRequest, qs: ProductQueryDep
) -> ProductBatchRead:
    """Читает товары пачкой по артикулам, отмечая отсутствующие."""
    batch = await qs.get_many(body.skus, include_deleted=body.include_deleted)
    return ProductBatchRead(
        products=[ProductRead.model_validate(view) for view in batch.products],
        missing_skus=list(batch.missing_skus),
    )


@router.get("/by-sku/{sku}", response_model=ProductRead, responses=_NOT_FOUND)
async def get_product_by_sku(
    sku: str, qs: ProductQueryDep, include_deleted: bool = False
) -> ProductRead:
    """Возвращает товар по артикулу."""
    view = await qs.get(sku=sku, include_deleted=include_deleted)
    if view is None:
        raise ProductNotFound(f"Товар не найден: {sku}")
    return ProductRead.model_validate(view)


@router.get("/{product_id}", response_model=ProductRead, responses=_NOT_FOUND)
async def get_product(
    product_id: ProductIdPath,
    qs: ProductQueryDep,
    include_deleted: bool = False,
) -> ProductRead:
    """Возвращает товар по идентификатору."""
    view = await qs.get(product_id=product_id, include_deleted=include_deleted)
    if view is None:
        raise ProductNotFound(f"Товар не найден: {product_id}")
    return ProductRead.model_validate(view)


@router.get(
    "/{product_id}/margin", response_model=MarginRead, responses=_NOT_FOUND
)
async def get_product_margin(
    product_id: ProductIdPath, qs: ProductQueryDep
) -> MarginRead:
    """Возвращает маржинальность товара."""
    view = await qs.get(product_id=product_id)
    if view is None:
        raise ProductNotFound(f"Товар не найден: {product_id}")
    return MarginRead.model_validate(view.margin)
