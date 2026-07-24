"""GET /health (liveness) и GET /ready (readiness)."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

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
