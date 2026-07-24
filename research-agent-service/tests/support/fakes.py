"""Переиспользуемые фейки для тестов use cases."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from research_agent_service.application.dto.answer import (
    AgentOutcome,
    RateVerdict,
)
from research_agent_service.application.outbox_message import OutboxMessage
from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.entities.conversation import Conversation
from research_agent_service.domain.entities.feedback import Feedback
from research_agent_service.domain.entities.message import Message
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
)

FIXED_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class FakeClock:
    """Часы с фиксированным моментом."""

    def now(self) -> datetime:
        return FIXED_NOW


class FakeIdGenerator:
    """Генератор последовательных UUID (детерминизм)."""

    def __init__(self) -> None:
        self._counter = 0

    def new_uuid7(self) -> UUID:
        self._counter += 1
        return UUID(int=self._counter)


class FakeConversationRepository:
    """Диалоги в памяти."""

    def __init__(self) -> None:
        self.added: list[Conversation] = []
        self.added_messages: list[Message] = []
        self.history: tuple[Message, ...] = ()
        self._store: dict[UUID, Conversation] = {}

    async def add(self, conversation: Conversation) -> None:
        self.added.append(conversation)
        self._store[conversation.id.value] = conversation

    async def get(self, conversation_id: ConversationId) -> Conversation | None:
        return self._store.get(conversation_id.value)

    async def add_message(self, message: Message) -> None:
        self.added_messages.append(message)

    async def load_history(
        self, conversation_id: ConversationId, *, limit: int
    ) -> tuple[Message, ...]:
        return self.history


class FakeAgentRunRepository:
    """Прогоны в памяти."""

    def __init__(self, *, run: AgentRun | None = None) -> None:
        self.added: list[AgentRun] = []
        self._run = run

    async def add(self, run: AgentRun) -> None:
        self.added.append(run)

    async def get(self, run_id: AgentRunId) -> AgentRun | None:
        return self._run

    async def list(self, **kwargs: object) -> tuple[AgentRun, ...]:
        return tuple(self.added)


class FakeFeedbackRepository:
    """Обратная связь в памяти."""

    def __init__(self) -> None:
        self.added: list[Feedback] = []

    async def add(self, feedback: Feedback) -> None:
        self.added.append(feedback)


class FakeOutboxRepository:
    """Outbox в памяти."""

    def __init__(self) -> None:
        self.messages: list[OutboxMessage] = []

    async def add_many(self, messages: Sequence[OutboxMessage]) -> None:
        self.messages.extend(messages)


class FakeUnitOfWork:
    """UnitOfWork в памяти: репозитории на «одной сессии», учёт commit."""

    def __init__(self, *, run: AgentRun | None = None) -> None:
        self.conversations = FakeConversationRepository()
        self.agent_runs = FakeAgentRunRepository(run=run)
        self.feedback = FakeFeedbackRepository()
        self.outbox = FakeOutboxRepository()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeRateLimiter:
    """Rate limiter с заранее заданным вердиктом."""

    def __init__(
        self, *, allowed: bool = True, retry_after_s: float | None = None
    ) -> None:
        self._verdict = RateVerdict(
            allowed=allowed, retry_after_s=retry_after_s
        )

    async def check(
        self, key: str, *, limit: int, window_s: int
    ) -> RateVerdict:
        return self._verdict


class FakeOrchestrator:
    """Оркестратор с заранее заданным исходом или ошибкой."""

    def __init__(
        self,
        *,
        outcome: AgentOutcome | None = None,
        error: Exception | None = None,
    ) -> None:
        self._outcome = outcome
        self._error = error
        self.history: tuple[object, ...] = ()

    async def run(
        self, query: object, history: tuple[object, ...], *, deadline_s: float
    ) -> AgentOutcome:
        self.history = history
        if self._error is not None:
            raise self._error
        if self._outcome is None:
            raise AssertionError("FakeOrchestrator без outcome и error")
        return self._outcome
