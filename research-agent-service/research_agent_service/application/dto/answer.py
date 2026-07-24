"""DTO пути ответа: команда, результат, исход оркестрации, вердикт лимита."""

from dataclasses import dataclass

from research_agent_service.domain.entities.tool_call import ToolCall
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import (
    Confidence,
    RunStatus,
    ToolName,
)
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
)
from research_agent_service.domain.value_objects.query import Query
from research_agent_service.domain.value_objects.usage import TokenUsage


@dataclass(frozen=True, slots=True)
class AnswerQueryCommand:
    """Вход use case AnswerQuery."""

    query: Query
    client_principal: str
    conversation_id: ConversationId | None = None
    trace_id: str | None = None
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentOutcome:
    """Результат оркестратора: ответ, источники, вызовы, provenance-рефы."""

    answer: str
    citations: tuple[Citation, ...]
    tool_calls: tuple[ToolCall, ...]
    usage: TokenUsage
    confidence: Confidence | None
    used_tools: tuple[ToolName, ...] = ()
    degradations: tuple[Degradation, ...] = ()
    retrieved_refs: tuple[str, ...] = ()
    web_refs: tuple[str, ...] = ()
    price_refs: tuple[str, ...] = ()
    loop_steps: int = 0


@dataclass(frozen=True, slots=True)
class AnswerQueryResult:
    """Ответ use case AnswerQuery клиенту."""

    agent_run_id: AgentRunId
    conversation_id: ConversationId
    status: RunStatus
    answer: str
    citations: tuple[Citation, ...]
    used_tools: tuple[ToolName, ...]
    confidence: Confidence | None
    degradations: tuple[Degradation, ...]
    usage: TokenUsage
    latency_ms: int


@dataclass(frozen=True, slots=True)
class RateVerdict:
    """Вердикт rate limiter'а."""

    allowed: bool
    retry_after_s: float | None = None
