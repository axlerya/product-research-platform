"""Обёртка стандартного gRPC Health Checking (§6.7).

``SERVING`` выставляется только после успешной загрузки+probe модели
(readiness, §8); при shutdown — ``NOT_SERVING``.
"""

from grpc_health.v1 import health, health_pb2

SERVING = health_pb2.HealthCheckResponse.SERVING
NOT_SERVING = health_pb2.HealthCheckResponse.NOT_SERVING


def build_health_servicer() -> health.aio.HealthServicer:
    """Асинхронный health-servicer (стартовый статус — не SERVING)."""
    return health.aio.HealthServicer()


async def set_serving(
    servicer: health.aio.HealthServicer,
    *,
    serving: bool,
    service: str = "",
) -> None:
    """Переключает статус здоровья (SERVING только после readiness)."""
    await servicer.set(service, SERVING if serving else NOT_SERVING)
