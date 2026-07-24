"""Порт AgentOrchestratorPort — исполнитель agent loop (LangGraph)."""

from typing import Protocol

from research_agent_service.application.dto.answer import AgentOutcome
from research_agent_service.domain.entities.message import Message
from research_agent_service.domain.value_objects.query import Query


class AgentOrchestratorPort(Protocol):
    """Оркестратор: выбирает инструменты и собирает ответ (без записи в БД)."""

    async def run(
        self,
        query: Query,
        history: tuple[Message, ...],
        *,
        deadline_s: float,
    ) -> AgentOutcome:
        """Прогоняет agent loop в пределах дедлайна и возвращает исход."""
        ...
