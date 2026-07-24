"""GET /queries, GET /queries/{id}, POST /queries/{id}/feedback."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from research_agent_service.application.exceptions import UnknownAgentRun
from research_agent_service.domain.value_objects.enums import RunStatus
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
)
from research_agent_service.presentation.api.dependencies import get_services
from research_agent_service.presentation.api.services import ApiServices
from research_agent_service.presentation.schemas.feedback import FeedbackRequest
from research_agent_service.presentation.schemas.mappers import (
    run_to_detail,
    run_to_summary,
)
from research_agent_service.presentation.schemas.queries import (
    QueryListResponse,
    RunDetail,
)

router = APIRouter(prefix="/queries", tags=["queries"])


@router.get("", response_model=QueryListResponse)
async def list_queries(
    services: ApiServices = Depends(get_services),
    conversation_id: UUID | None = Query(default=None),
    status_filter: RunStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> QueryListResponse:
    """Возвращает страницу прогонов с фильтрами."""
    runs = await services.list_queries.execute(
        conversation_id=(
            ConversationId(conversation_id)
            if conversation_id is not None
            else None
        ),
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return QueryListResponse(
        items=[run_to_summary(run) for run in runs],
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=RunDetail)
async def get_query(
    run_id: UUID,
    services: ApiServices = Depends(get_services),
) -> RunDetail:
    """Возвращает детали прогона; 404, если не найден."""
    run = await services.get_query.execute(AgentRunId(run_id))
    if run is None:
        raise UnknownAgentRun(str(run_id))
    return run_to_detail(run)


@router.post(
    "/{run_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def submit_feedback(
    run_id: UUID,
    body: FeedbackRequest,
    services: ApiServices = Depends(get_services),
) -> None:
    """Принимает обратную связь по прогону (204)."""
    await services.submit_feedback.execute(body.to_command(AgentRunId(run_id)))
