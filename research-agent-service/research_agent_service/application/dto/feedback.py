"""DTO обратной связи."""

from dataclasses import dataclass

from research_agent_service.domain.value_objects.enums import FeedbackRating
from research_agent_service.domain.value_objects.identifiers import AgentRunId


@dataclass(frozen=True, slots=True)
class SubmitFeedbackCommand:
    """Вход use case SubmitFeedback."""

    agent_run_id: AgentRunId
    rating: FeedbackRating
    reason: str | None = None
    labels: tuple[str, ...] = ()
