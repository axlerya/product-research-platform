"""POST /query — синхронный путь ответа (не зависит от RabbitMQ)."""

import time

from fastapi import APIRouter, Depends, Header

from research_agent_service.application.exceptions import RateLimited
from research_agent_service.presentation.api.dependencies import get_services
from research_agent_service.presentation.api.services import ApiServices
from research_agent_service.presentation.schemas.mappers import (
    answer_result_to_response,
)
from research_agent_service.presentation.schemas.query import (
    QueryRequest,
    QueryResponse,
)

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def create_query(
    body: QueryRequest,
    services: ApiServices = Depends(get_services),
    x_client_principal: str = Header(default="anonymous"),
    x_trace_id: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
) -> QueryResponse:
    """Обрабатывает запрос агентом и возвращает структурированный ответ."""
    command = body.to_command(
        client_principal=x_client_principal,
        trace_id=x_trace_id,
        correlation_id=x_correlation_id,
    )
    metrics = services.metrics
    if metrics is not None:
        metrics.run_started()
    started = time.perf_counter()
    try:
        result = await services.answer_query.execute(command)
    except RateLimited:
        if metrics is not None:
            metrics.rate_limited()
        raise
    finally:
        if metrics is not None:
            metrics.run_finished()
    if metrics is not None:
        metrics.observe_query(result, latency_s=time.perf_counter() - started)
    return answer_result_to_response(result)
