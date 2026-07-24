"""Сущность AgentRun — прогон агента над одним запросом."""

from datetime import datetime

from research_agent_service.domain.entities.tool_call import ToolCall
from research_agent_service.domain.exceptions import RunAlreadyFinalized
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import (
    Confidence,
    RunStatus,
)
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    MessageId,
)
from research_agent_service.domain.value_objects.run_error import RunError
from research_agent_service.domain.value_objects.usage import TokenUsage

_TERMINAL_STATUSES = frozenset(
    {RunStatus.COMPLETED, RunStatus.DEGRADED, RunStatus.FAILED}
)


class AgentRun:
    """Агрегат-корень прогона агента.

    Создаётся в состоянии RUNNING; владеет своими вызовами инструментов.
    Жизненный цикл монотонен: RUNNING → {COMPLETED | DEGRADED | FAILED};
    терминальный статус неизменяем. Мутирующие методы принимают ``now``
    явно (детерминизм).
    """

    __slots__ = (
        "answer_message_id",
        "client_principal",
        "confidence",
        "conversation_id",
        "correlation_id",
        "degradations",
        "error",
        "finished_at",
        "id",
        "idempotency_key",
        "loop_steps",
        "model",
        "prompt_version",
        "query_message_id",
        "started_at",
        "status",
        "tool_calls",
        "trace_id",
        "usage",
    )

    def __init__(
        self,
        *,
        id: AgentRunId,
        conversation_id: ConversationId,
        query_message_id: MessageId,
        model: str,
        prompt_version: str,
        started_at: datetime,
        client_principal: str | None = None,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.id = id
        self.conversation_id = conversation_id
        self.query_message_id = query_message_id
        self.model = model
        self.prompt_version = prompt_version
        self.started_at = started_at
        self.client_principal = client_principal
        self.idempotency_key = idempotency_key
        self.trace_id = trace_id
        self.correlation_id = correlation_id
        self.status = RunStatus.RUNNING
        self.finished_at: datetime | None = None
        self.usage = TokenUsage(prompt_tokens=0, completion_tokens=0)
        self.loop_steps = 0
        self.confidence: Confidence | None = None
        self.answer_message_id: MessageId | None = None
        self.degradations: tuple[Degradation, ...] = ()
        self.error: RunError | None = None
        self.tool_calls: list[ToolCall] = []

    @property
    def tool_call_count(self) -> int:
        """Число вызовов инструментов в прогоне."""
        return len(self.tool_calls)

    def record_tool_call(self, tool_call: ToolCall) -> None:
        """Добавляет вызов инструмента к прогону."""
        self._ensure_active()
        self.tool_calls.append(tool_call)

    def complete(
        self,
        *,
        answer_message_id: MessageId,
        usage: TokenUsage,
        confidence: Confidence,
        degradations: tuple[Degradation, ...],
        loop_steps: int,
        now: datetime,
    ) -> None:
        """Успешно завершает прогон.

        Наличие деградаций переводит прогон в DEGRADED, иначе — COMPLETED.
        """
        self._ensure_active()
        self.answer_message_id = answer_message_id
        self.usage = usage
        self.confidence = confidence
        self.degradations = degradations
        self.loop_steps = loop_steps
        self.finished_at = now
        self.status = (
            RunStatus.DEGRADED if degradations else RunStatus.COMPLETED
        )

    def fail(self, *, error: RunError, now: datetime) -> None:
        """Переводит прогон в FAILED, сохраняя структурированную ошибку."""
        self._ensure_active()
        self.error = error
        self.finished_at = now
        self.status = RunStatus.FAILED

    def _ensure_active(self) -> None:
        if self.status in _TERMINAL_STATUSES:
            raise RunAlreadyFinalized(
                f"Прогон уже финализирован: {self.status}"
            )
