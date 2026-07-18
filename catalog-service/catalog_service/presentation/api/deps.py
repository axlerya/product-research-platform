"""DI-провайдеры use cases.

По умолчанию не связаны (бросают ``NotImplementedError``): конкретные
реализации внедряет composition root через ``dependency_overrides``.
"""

from typing import Annotated

from fastapi import Depends

from catalog_service.application.ports.read_models import (
    ProductQueryService,
    ReferenceQueryService,
)
from catalog_service.application.use_cases.create_product import CreateProduct
from catalog_service.application.use_cases.delete_product import DeleteProduct
from catalog_service.application.use_cases.set_stock import SetStock
from catalog_service.application.use_cases.update_commercial_data import (
    UpdateCommercialData,
)
from catalog_service.application.use_cases.update_metrics import UpdateMetrics
from catalog_service.application.use_cases.update_product_content import (
    UpdateProductContent,
)

_UNWIRED = "Use case не связан — переопределите провайдер в composition root"


def get_create_product_uc() -> CreateProduct:
    raise NotImplementedError(_UNWIRED)


def get_update_content_uc() -> UpdateProductContent:
    raise NotImplementedError(_UNWIRED)


def get_update_commercial_uc() -> UpdateCommercialData:
    raise NotImplementedError(_UNWIRED)


def get_set_stock_uc() -> SetStock:
    raise NotImplementedError(_UNWIRED)


def get_update_metrics_uc() -> UpdateMetrics:
    raise NotImplementedError(_UNWIRED)


def get_delete_product_uc() -> DeleteProduct:
    raise NotImplementedError(_UNWIRED)


CreateProductDep = Annotated[CreateProduct, Depends(get_create_product_uc)]
UpdateContentDep = Annotated[
    UpdateProductContent, Depends(get_update_content_uc)
]
UpdateCommercialDep = Annotated[
    UpdateCommercialData, Depends(get_update_commercial_uc)
]
SetStockDep = Annotated[SetStock, Depends(get_set_stock_uc)]
UpdateMetricsDep = Annotated[UpdateMetrics, Depends(get_update_metrics_uc)]
DeleteProductDep = Annotated[DeleteProduct, Depends(get_delete_product_uc)]


def get_product_query_service() -> ProductQueryService:
    raise NotImplementedError(_UNWIRED)


def get_reference_query_service() -> ReferenceQueryService:
    raise NotImplementedError(_UNWIRED)


ProductQueryDep = Annotated[
    ProductQueryService, Depends(get_product_query_service)
]
ReferenceQueryDep = Annotated[
    ReferenceQueryService, Depends(get_reference_query_service)
]
