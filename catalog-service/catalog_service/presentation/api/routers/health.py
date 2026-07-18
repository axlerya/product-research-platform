"""Health/readiness эндпоинты (вне версии API)."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: сервис жив (без обращения к зависимостям)."""
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness (заглушка; проверка БД/брокера — в composition root)."""
    return {"status": "ready"}
