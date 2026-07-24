"""GET /health (liveness), GET /ready (readiness), GET /metrics."""

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from research_agent_service.infrastructure.observability.metrics import (
    METRICS_CONTENT_TYPE,
)
from research_agent_service.presentation.api.dependencies import get_services
from research_agent_service.presentation.api.services import ApiServices

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: процесс жив."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    services: ApiServices = Depends(get_services),
) -> JSONResponse:
    """Readiness: зависимости готовы (иначе 503)."""
    if await services.readiness():
        return JSONResponse(status_code=200, content={"status": "ready"})
    return JSONResponse(status_code=503, content={"status": "not_ready"})


@router.get("/metrics")
async def metrics(
    services: ApiServices = Depends(get_services),
) -> Response:
    """Отдаёт метрики Prometheus (404, если запись метрик не подключена)."""
    recorder = services.metrics
    if recorder is None:
        return Response(status_code=404)
    return Response(content=recorder.render(), media_type=METRICS_CONTENT_TYPE)
