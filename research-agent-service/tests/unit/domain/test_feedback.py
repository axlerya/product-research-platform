"""Тесты сущности Feedback."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from research_agent_service.domain.entities.feedback import Feedback
from research_agent_service.domain.value_objects.enums import FeedbackRating
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ConversationId,
    FeedbackId,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_feedback_holds_fields_and_defaults() -> None:
    """Обязательные поля сохраняются; reason/labels — по умолчанию."""
    feedback = Feedback(
        id=FeedbackId.new(),
        agent_run_id=AgentRunId.new(),
        conversation_id=ConversationId.new(),
        rating=FeedbackRating.UP,
        created_at=_NOW,
    )

    assert feedback.rating is FeedbackRating.UP
    assert feedback.reason is None
    assert feedback.labels == ()


def test_negative_feedback_carries_reason_and_labels() -> None:
    """Негативная оценка несёт причину и метки."""
    feedback = Feedback(
        id=FeedbackId.new(),
        agent_run_id=AgentRunId.new(),
        conversation_id=ConversationId.new(),
        rating=FeedbackRating.DOWN,
        created_at=_NOW,
        reason="неточные цены",
        labels=("pricing",),
    )

    assert feedback.reason == "неточные цены"
    assert feedback.labels == ("pricing",)


def test_feedback_is_frozen() -> None:
    """Feedback неизменяем."""
    feedback = Feedback(
        id=FeedbackId.new(),
        agent_run_id=AgentRunId.new(),
        conversation_id=ConversationId.new(),
        rating=FeedbackRating.UP,
        created_at=_NOW,
    )

    with pytest.raises(FrozenInstanceError):
        feedback.rating = FeedbackRating.DOWN
