"""Use case AnswerQuery — синхронный оркестратор запроса.

Поток: rate limit → диалог/сообщение пользователя → прогон → оркестрация →
проверка источников (INV-2) → атомарная финализация вместе с outbox.
Agent run, tool calls и событие сохраняются в ОДНОЙ транзакции.
"""

import hashlib
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from research_agent_service.application.dto.answer import (
    AgentOutcome,
    AnswerQueryCommand,
    AnswerQueryResult,
)
from research_agent_service.application.event_mapping import (
    build_query_completed_message,
    build_query_failed_message,
)
from research_agent_service.application.exceptions import (
    QueryFailed,
    RateLimited,
)
from research_agent_service.application.outbox_message import OutboxMessage
from research_agent_service.application.ports.cache import CachePort
from research_agent_service.application.ports.clock import Clock
from research_agent_service.application.ports.id_generator import IdGenerator
from research_agent_service.application.ports.orchestrator import (
    AgentOrchestratorPort,
)
from research_agent_service.application.ports.rate_limiter import (
    RateLimiterPort,
)
from research_agent_service.application.ports.uow import UnitOfWork
from research_agent_service.application.services.source_validation import (
    SourceValidator,
)
from research_agent_service.domain.entities.agent_run import AgentRun
from research_agent_service.domain.entities.conversation import Conversation
from research_agent_service.domain.entities.message import Message
from research_agent_service.domain.policies import (
    DEFAULT_AGENT_LOOP_POLICY,
    AgentLoopPolicy,
)
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import (
    Confidence,
    ErrorCategory,
    ErrorCode,
    MessageRole,
    RunStage,
)
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    MessageId,
)
from research_agent_service.domain.value_objects.run_error import RunError

_RATE_LIMIT = 60
_RATE_WINDOW_S = 60
_HISTORY_LIMIT = 10
_ERROR_MESSAGE_MAX = 500
_IDEMPOTENCY_TTL_S = 86400


def _query_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _latency_ms(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() * 1000)


class AnswerQueryUseCase:
    """Синхронный обработчик POST /query (не зависит от RabbitMQ)."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        orchestrator: AgentOrchestratorPort,
        rate_limiter: RateLimiterPort,
        source_validator: SourceValidator,
        id_generator: IdGenerator,
        clock: Clock,
        policy: AgentLoopPolicy = DEFAULT_AGENT_LOOP_POLICY,
        model: str = "claude-opus-4-8",
        prompt_version: str = "v1",
        cache: CachePort | None = None,
        idempotency_ttl_s: int = _IDEMPOTENCY_TTL_S,
    ) -> None:
        self._uow = uow
        self._orchestrator = orchestrator
        self._rate_limiter = rate_limiter
        self._validator = source_validator
        self._ids = id_generator
        self._clock = clock
        self._policy = policy
        self._model = model
        self._prompt_version = prompt_version
        self._cache = cache
        self._idempotency_ttl_s = idempotency_ttl_s

    async def execute(self, command: AnswerQueryCommand) -> AnswerQueryResult:
        """Обрабатывает запрос и возвращает структурированный ответ."""
        started = self._clock.now()
        verdict = await self._rate_limiter.check(
            command.client_principal,
            limit=_RATE_LIMIT,
            window_s=_RATE_WINDOW_S,
        )
        if not verdict.allowed:
            raise RateLimited(retry_after_s=verdict.retry_after_s)

        replayed = await self._replay(command)
        if replayed is not None:
            return replayed

        query_hash = _query_hash(command.query.text)
        conversation, history, is_new = await self._resolve_conversation(
            command, started
        )
        user_message = Message(
            id=MessageId(self._ids.new_uuid7()),
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=command.query.text,
            created_at=started,
        )
        run = self._new_run(command, conversation, user_message, started)

        try:
            outcome = await self._orchestrator.run(
                command.query,
                history,
                deadline_s=self._policy.wall_clock_budget_s,
            )
        except Exception as exc:
            await self._finalize_failed(
                conversation, is_new, user_message, run, query_hash, exc
            )
            raise QueryFailed(run.id) from exc

        result = await self._finalize_completed(
            conversation,
            is_new,
            user_message,
            run,
            outcome,
            query_hash,
            started,
        )
        await self._remember(command, result)
        return result

    async def _replay(
        self, command: AnswerQueryCommand
    ) -> AnswerQueryResult | None:
        """Возвращает прежний результат по idempotency_key (или None)."""
        key = self._idempotency_key(command)
        if key is None:
            return None
        cached = await self._cache.get(key)
        if cached is None:
            return None
        run_id = AgentRunId(UUID(cached))
        async with self._uow as uow:
            run = await uow.agent_runs.get(run_id)
            if run is None or run.answer_message_id is None:
                return None
            message = await uow.conversations.get_message(run.answer_message_id)
        if message is None:
            return None
        return self._result_from_run(run, message)

    async def _remember(
        self, command: AnswerQueryCommand, result: AnswerQueryResult
    ) -> None:
        """Запоминает id прогона под idempotency_key для повторов."""
        key = self._idempotency_key(command)
        if key is None:
            return
        await self._cache.set(
            key,
            str(result.agent_run_id.value),
            ttl_s=self._idempotency_ttl_s,
        )

    def _idempotency_key(self, command: AnswerQueryCommand) -> str | None:
        if self._cache is None or command.query.idempotency_key is None:
            return None
        return (
            f"idem:{command.client_principal}:{command.query.idempotency_key}"
        )

    def _result_from_run(
        self, run: AgentRun, answer: Message
    ) -> AnswerQueryResult:
        # Реплеятся только завершённые прогоны (answer_message_id задан),
        # поэтому finished_at гарантированно проставлен (datetime, не None).
        return AnswerQueryResult(
            agent_run_id=run.id,
            conversation_id=run.conversation_id,
            status=run.status,
            answer=answer.content,
            citations=answer.citations,
            used_tools=self._used_tools(run),
            confidence=run.confidence,
            degradations=run.degradations,
            usage=run.usage,
            latency_ms=_latency_ms(run.started_at, run.finished_at),
        )

    @staticmethod
    def _used_tools(run: AgentRun) -> tuple:
        return tuple(dict.fromkeys(call.tool for call in run.tool_calls))

    def _new_run(
        self,
        command: AnswerQueryCommand,
        conversation: Conversation,
        user_message: Message,
        started: datetime,
    ) -> AgentRun:
        return AgentRun(
            id=AgentRunId(self._ids.new_uuid7()),
            conversation_id=conversation.id,
            query_message_id=user_message.id,
            model=self._model,
            prompt_version=self._prompt_version,
            started_at=started,
            client_principal=command.client_principal,
            idempotency_key=command.query.idempotency_key,
            trace_id=command.trace_id,
            correlation_id=command.correlation_id,
        )

    async def _resolve_conversation(
        self, command: AnswerQueryCommand, now: datetime
    ) -> tuple[Conversation, tuple[Message, ...], bool]:
        if command.conversation_id is None:
            fresh = Conversation(
                id=ConversationId(self._ids.new_uuid7()), created_at=now
            )
            return fresh, (), True
        async with self._uow as uow:
            existing = await uow.conversations.get(command.conversation_id)
            history = await uow.conversations.load_history(
                command.conversation_id, limit=_HISTORY_LIMIT
            )
        if existing is None:
            fresh = Conversation(id=command.conversation_id, created_at=now)
            return fresh, history, True
        return existing, history, False

    async def _finalize_failed(
        self,
        conversation: Conversation,
        is_new: bool,
        user_message: Message,
        run: AgentRun,
        query_hash: str,
        exc: Exception,
    ) -> None:
        failed_at = self._clock.now()
        run.fail(
            error=RunError(
                code=ErrorCode.INTERNAL,
                category=ErrorCategory.INTERNAL,
                stage=RunStage.PLAN,
                message=str(exc)[:_ERROR_MESSAGE_MAX],
            ),
            now=failed_at,
        )
        message = build_query_failed_message(
            run,
            event_id=self._ids.new_uuid7(),
            query_hash=query_hash,
            occurred_at=failed_at,
        )
        await self._persist(
            conversation, is_new, user_message, run, None, [message]
        )

    async def _finalize_completed(
        self,
        conversation: Conversation,
        is_new: bool,
        user_message: Message,
        run: AgentRun,
        outcome: AgentOutcome,
        query_hash: str,
        started: datetime,
    ) -> AnswerQueryResult:
        validated = self._validator.validate(
            outcome.citations,
            product_refs=frozenset(outcome.retrieved_refs),
            web_refs=frozenset(outcome.web_refs),
            price_refs=frozenset(outcome.price_refs),
        )
        finished = self._clock.now()
        degradations = self._degradations(outcome, validated)
        answer_message = Message(
            id=MessageId(self._ids.new_uuid7()),
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=outcome.answer,
            created_at=finished,
            agent_run_id=run.id,
            citations=validated,
            token_count=outcome.usage.completion_tokens,
        )
        for tool_call in outcome.tool_calls:
            run.record_tool_call(replace(tool_call, agent_run_id=run.id))
        run.complete(
            answer_message_id=answer_message.id,
            usage=outcome.usage,
            confidence=outcome.confidence or Confidence.LOW,
            degradations=degradations,
            loop_steps=outcome.loop_steps,
            now=finished,
        )
        message = build_query_completed_message(
            run,
            validated,
            event_id=self._ids.new_uuid7(),
            query_hash=query_hash,
            occurred_at=finished,
        )
        await self._persist(
            conversation, is_new, user_message, run, answer_message, [message]
        )
        return AnswerQueryResult(
            agent_run_id=run.id,
            conversation_id=conversation.id,
            status=run.status,
            answer=outcome.answer,
            citations=validated,
            used_tools=outcome.used_tools,
            confidence=run.confidence,
            degradations=run.degradations,
            usage=run.usage,
            latency_ms=_latency_ms(started, finished),
        )

    @staticmethod
    def _degradations(
        outcome: AgentOutcome, validated: tuple[Citation, ...]
    ) -> tuple[Degradation, ...]:
        extra: tuple[Degradation, ...] = ()
        if len(validated) < len(outcome.citations):
            extra = (Degradation("citations", "dangling_dropped"),)
        return tuple(outcome.degradations) + extra

    async def _persist(
        self,
        conversation: Conversation,
        is_new: bool,
        user_message: Message,
        run: AgentRun,
        answer_message: Message | None,
        outbox: Iterable[OutboxMessage],
    ) -> None:
        async with self._uow as uow:
            if is_new:
                await uow.conversations.add(conversation)
            await uow.conversations.add_message(user_message)
            conversation.record_message(now=user_message.created_at)
            if answer_message is not None:
                await uow.conversations.add_message(answer_message)
                conversation.record_message(now=answer_message.created_at)
            await uow.agent_runs.add(run)
            await uow.outbox.add_many(list(outbox))
            await uow.commit()
