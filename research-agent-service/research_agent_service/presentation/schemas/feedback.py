"""Схема POST /feedback."""

from pydantic import BaseModel, ConfigDict

from research_agent_service.application.dto.feedback import (
    SubmitFeedbackCommand,
)
from research_agent_service.domain.value_objects.enums import FeedbackRating
from research_agent_service.domain.value_objects.identifiers import AgentRunId


class FeedbackRequest(BaseModel):
    """Тело POST /queries/{id}/feedback."""

    model_config = ConfigDict(extra="forbid")

    rating: FeedbackRating
    reason: str | None = None
    labels: list[str] = []

    def to_command(self, run_id: AgentRunId) -> SubmitFeedbackCommand:
        """Строит команду use case для указанного прогона."""
        return SubmitFeedbackCommand(
            agent_run_id=run_id,
            rating=self.rating,
            reason=self.reason,
            labels=tuple(self.labels),
        )
