"""Роутер справочников (категории/бренды/поставщики)."""

from fastapi import APIRouter

from catalog_service.presentation.api.deps import ReferenceQueryDep
from catalog_service.presentation.api.schemas.reads import ReferenceRead

router = APIRouter(prefix="/api/v1", tags=["references"])


@router.get("/categories", response_model=list[ReferenceRead])
async def list_categories(qs: ReferenceQueryDep) -> list[ReferenceRead]:
    """Список категорий с числом активных товаров."""
    return [
        ReferenceRead.model_validate(ref) for ref in await qs.list_categories()
    ]


@router.get("/brands", response_model=list[ReferenceRead])
async def list_brands(qs: ReferenceQueryDep) -> list[ReferenceRead]:
    """Список брендов с числом активных товаров."""
    return [ReferenceRead.model_validate(ref) for ref in await qs.list_brands()]


@router.get("/suppliers", response_model=list[ReferenceRead])
async def list_suppliers(qs: ReferenceQueryDep) -> list[ReferenceRead]:
    """Список поставщиков с числом активных товаров."""
    return [
        ReferenceRead.model_validate(ref) for ref in await qs.list_suppliers()
    ]
