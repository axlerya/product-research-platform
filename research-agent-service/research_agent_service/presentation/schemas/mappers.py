"""Мапперы домен/DTO → схемы ответа API."""

from research_agent_service.application.dto.answer import AnswerQueryResult
from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.usage import TokenUsage
from research_agent_service.presentation.schemas.common import (
    CitationSchema,
    DegradationSchema,
    UsageSchema,
)
from research_agent_service.presentation.schemas.queries import (
    RunDetail,
    RunSummary,
)
from research_agent_service.presentation.schemas.query import QueryResponse


def _usage(usage: TokenUsage) -> UsageSchema:
    return UsageSchema(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total,
    )


def _citation(citation: Citation) -> CitationSchema:
    return CitationSchema(
        source_type=citation.source_type,
        ref=citation.ref,
        title=citation.title,
        snippet=citation.snippet,
        position=citation.position,
        score=None if citation.score is None else str(citation.score),
    )


def _degradation(degradation: Degradation) -> DegradationSchema:
    return DegradationSchema(
        dependency=degradation.dependency, reason=degradation.reason
    )


def answer_result_to_response(result: AnswerQueryResult) -> QueryResponse:
    """AnswerQueryResult → тело ответа POST /query."""
    return QueryResponse(
        agent_run_id=result.agent_run_id.value,
        conversation_id=result.conversation_id.value,
        status=result.status,
        answer=result.answer,
        citations=[_citation(c) for c in result.citations],
        used_tools=[tool.value for tool in result.used_tools],
        confidence=result.confidence,
        degradations=[_degradation(d) for d in result.degradations],
        usage=_usage(result.usage),
        latency_ms=result.latency_ms,
    )


def run_to_summary(run: AgentRun) -> RunSummary:
    """AgentRun → краткая карточка списка."""
    return RunSummary(
        agent_run_id=run.id.value,
        conversation_id=run.conversation_id.value,
        status=run.status,
        model=run.model,
        confidence=run.confidence,
        tool_call_count=run.tool_call_count,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def run_to_detail(run: AgentRun) -> RunDetail:
    """AgentRun → детальная карточка прогона."""
    return RunDetail(
        agent_run_id=run.id.value,
        conversation_id=run.conversation_id.value,
        status=run.status,
        model=run.model,
        confidence=run.confidence,
        tool_call_count=run.tool_call_count,
        started_at=run.started_at,
        finished_at=run.finished_at,
        usage=_usage(run.usage),
        degradations=[_degradation(d) for d in run.degradations],
        loop_steps=run.loop_steps,
        error_code=None if run.error is None else run.error.code.value,
    )
