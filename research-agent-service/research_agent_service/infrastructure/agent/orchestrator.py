"""LangGraphOrchestrator — реализация порта AgentOrchestratorPort.

Строит стартовое состояние, прогоняет граф в пределах дедлайна и переводит
итог в AgentOutcome. Confidence считается детерминированно (не моделью):
есть источники и нет деградаций → HIGH, есть источники с деградациями →
MEDIUM, источников нет → LOW.
"""

import time
from collections.abc import Callable, Iterable
from typing import Any

from research_agent_service.application.dto.answer import AgentOutcome
from research_agent_service.application.ports.id_generator import IdGenerator
from research_agent_service.domain.entities.message import Message
from research_agent_service.domain.policies import (
    DEFAULT_AGENT_LOOP_POLICY,
    AgentLoopPolicy,
)
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import Confidence
from research_agent_service.domain.value_objects.identifiers import AgentRunId
from research_agent_service.domain.value_objects.query import Query
from research_agent_service.domain.value_objects.usage import TokenUsage
from research_agent_service.infrastructure.agent.executor import ToolExecutor
from research_agent_service.infrastructure.agent.graph import build_agent_graph
from research_agent_service.infrastructure.agent.prompts import build_messages

_RECURSION_LIMIT = 50


class LangGraphOrchestrator:
    """Оркестратор agent loop на LangGraph (без записи в БД)."""

    def __init__(
        self,
        *,
        model: Any,
        executor: ToolExecutor,
        id_generator: IdGenerator,
        policy: AgentLoopPolicy = DEFAULT_AGENT_LOOP_POLICY,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._graph = build_agent_graph(
            model=model,
            executor=executor,
            policy=policy,
            monotonic=monotonic,
        )
        self._ids = id_generator
        self._monotonic = monotonic

    async def run(
        self,
        query: Query,
        history: tuple[Message, ...],
        *,
        deadline_s: float,
    ) -> AgentOutcome:
        """Прогоняет agent loop и возвращает исход (tool_calls — черновые)."""
        run_id = AgentRunId(self._ids.new_uuid7())
        state = {
            "messages": build_messages(query, history),
            "steps": 0,
            "tool_call_total": 0,
            "tool_calls": [],
            "citations": [],
            "product_refs": [],
            "web_refs": [],
            "price_refs": [],
            "degradations": [],
            "used_tools": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "run_id": run_id,
            "deadline_at": self._monotonic() + deadline_s,
        }
        final = await self._graph.ainvoke(
            state, config={"recursion_limit": _RECURSION_LIMIT}
        )
        return _to_outcome(final)


def _to_outcome(state: dict[str, Any]) -> AgentOutcome:
    citations = tuple(state["citations"])
    degradations = _unique(state["degradations"])
    return AgentOutcome(
        answer=_text(state["messages"][-1].content),
        citations=citations,
        tool_calls=tuple(state["tool_calls"]),
        usage=TokenUsage(
            prompt_tokens=state["prompt_tokens"],
            completion_tokens=state["completion_tokens"],
        ),
        confidence=_confidence(citations, degradations),
        used_tools=_unique(state["used_tools"]),
        degradations=degradations,
        retrieved_refs=_unique(state["product_refs"]),
        web_refs=_unique(state["web_refs"]),
        price_refs=_unique(state["price_refs"]),
        loop_steps=state["steps"],
    )


def _confidence(
    citations: tuple[Citation, ...], degradations: tuple[Degradation, ...]
) -> Confidence:
    if not citations:
        return Confidence.LOW
    return Confidence.MEDIUM if degradations else Confidence.HIGH


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part["text"] if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


def _unique(items: Iterable[Any]) -> tuple[Any, ...]:
    return tuple(dict.fromkeys(items))
