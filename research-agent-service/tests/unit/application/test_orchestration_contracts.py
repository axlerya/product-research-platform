"""Тесты контрактов оркестрации и поддержки (DTO + порты)."""

from research_agent_service.application.dto.answer import (
    AgentOutcome,
    AnswerQueryCommand,
    RateVerdict,
)
from research_agent_service.application.ports.cache import CachePort
from research_agent_service.application.ports.id_generator import IdGenerator
from research_agent_service.application.ports.orchestrator import (
    AgentOrchestratorPort,
)
from research_agent_service.application.ports.publisher import EventPublisher
from research_agent_service.application.ports.rate_limiter import (
    RateLimiterPort,
)
from research_agent_service.domain.value_objects.query import Query
from research_agent_service.domain.value_objects.usage import TokenUsage


def test_rate_verdict_default_allowed() -> None:
    """RateVerdict без retry_after → None по умолчанию."""
    verdict = RateVerdict(allowed=True)

    assert verdict.retry_after_s is None


def test_agent_outcome_defaults() -> None:
    """AgentOutcome: коллекции пусты, loop_steps=0 по умолчанию."""
    outcome = AgentOutcome(
        answer="ответ",
        citations=(),
        tool_calls=(),
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
        confidence=None,
    )

    assert outcome.used_tools == ()
    assert outcome.loop_steps == 0
    assert outcome.retrieved_refs == ()


def test_answer_query_command_defaults() -> None:
    """AnswerQueryCommand: conversation_id/trace_id опциональны."""
    cmd = AnswerQueryCommand(query=Query(text="привет"), client_principal="c1")

    assert cmd.conversation_id is None
    assert cmd.trace_id is None


def test_support_ports_expose_methods() -> None:
    """Порты поддержки и оркестрации определяют ожидаемые методы."""
    assert hasattr(CachePort, "get")
    assert hasattr(RateLimiterPort, "check")
    assert hasattr(IdGenerator, "new_uuid7")
    assert hasattr(EventPublisher, "publish")
    assert hasattr(AgentOrchestratorPort, "run")
