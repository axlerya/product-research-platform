"""Use case SubmitFeedback — приём обратной связи и триггер оценки."""

from research_agent_service.application.dto.feedback import (
    SubmitFeedbackCommand,
)
from research_agent_service.application.event_mapping import (
    build_evaluation_requested_message,
    build_feedback_received_message,
)
from research_agent_service.application.exceptions import UnknownAgentRun
from research_agent_service.application.outbox_message import OutboxMessage
from research_agent_service.application.ports.clock import Clock
from research_agent_service.application.ports.id_generator import IdGenerator
from research_agent_service.application.ports.uow import UnitOfWork
from research_agent_service.domain.entities.feedback import Feedback
from research_agent_service.domain.value_objects.enums import FeedbackRating
from research_agent_service.domain.value_objects.identifiers import FeedbackId

_EVALUATION_ON_NEGATIVE = "negative_feedback"


class SubmitFeedbackUseCase:
    """Сохраняет обратную связь и публикует события в одной транзакции.

    На негативную оценку дополнительно запрашивается оценка прогона
    (agent.evaluation.requested.v1). Всё — атомарно с outbox.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        id_generator: IdGenerator,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._ids = id_generator
        self._clock = clock

    async def execute(self, command: SubmitFeedbackCommand) -> None:
        """Сохраняет обратную связь и эмитит события."""
        now = self._clock.now()
        async with self._uow as uow:
            run = await uow.agent_runs.get(command.agent_run_id)
            if run is None:
                raise UnknownAgentRun(str(command.agent_run_id.value))
            feedback = Feedback(
                id=FeedbackId(self._ids.new_uuid7()),
                agent_run_id=command.agent_run_id,
                conversation_id=run.conversation_id,
                rating=command.rating,
                created_at=now,
                reason=command.reason,
                labels=command.labels,
            )
            await uow.feedback.add(feedback)
            messages: list[OutboxMessage] = [
                build_feedback_received_message(
                    feedback, event_id=self._ids.new_uuid7(), occurred_at=now
                )
            ]
            if command.rating is FeedbackRating.DOWN:
                messages.append(
                    build_evaluation_requested_message(
                        evaluation_id=self._ids.new_uuid7(),
                        agent_run_id=command.agent_run_id,
                        reason=_EVALUATION_ON_NEGATIVE,
                        event_id=self._ids.new_uuid7(),
                        occurred_at=now,
                    )
                )
            await uow.outbox.add_many(messages)
            await uow.commit()
