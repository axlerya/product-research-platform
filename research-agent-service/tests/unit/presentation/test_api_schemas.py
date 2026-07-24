"""Тесты схем запросов API (валидация и перевод в команды)."""

from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from research_agent_service.domain.exceptions import EmptyQuery
from research_agent_service.domain.value_objects.enums import FeedbackRating
from research_agent_service.domain.value_objects.identifiers import AgentRunId
from research_agent_service.presentation.schemas.feedback import FeedbackRequest
from research_agent_service.presentation.schemas.query import (
    QueryFiltersSchema,
    QueryRequest,
)


def test_query_request_to_command_builds_domain_query() -> None:
    """Запрос переводится в команду с доменным Query и фасетами."""
    request = QueryRequest(
        text="  найди наушники  ",
        conversation_id=UUID(int=5),
        filters=QueryFiltersSchema(category="Аудио", price_min=Decimal("10")),
    )

    command = request.to_command(
        client_principal="client-1", trace_id="t", correlation_id="cor"
    )

    assert command.query.text == "найди наушники"
    assert command.query.filters.category == "Аудио"
    assert command.query.filters.price_min == Decimal("10")
    assert command.conversation_id.value == UUID(int=5)
    assert command.client_principal == "client-1"
    assert command.trace_id == "t"


def test_query_request_without_conversation() -> None:
    """Без conversation_id команда несёт None."""
    command = QueryRequest(text="вопрос").to_command(
        client_principal="c", trace_id=None, correlation_id=None
    )
    assert command.conversation_id is None
    assert command.query.filters is None


def test_query_request_forbids_extra_fields() -> None:
    """Лишние поля в теле отклоняются."""
    with pytest.raises(ValidationError):
        QueryRequest(text="x", injected="DROP TABLE")


def test_query_request_rejects_empty_text() -> None:
    """Пустой text не проходит схему."""
    with pytest.raises(ValidationError):
        QueryRequest(text="")


def test_query_request_whitespace_text_raises_domain() -> None:
    """Пробельный text проходит схему, но домен его отвергает."""
    with pytest.raises(EmptyQuery):
        QueryRequest(text="   ").to_command(
            client_principal="c", trace_id=None, correlation_id=None
        )


def test_feedback_request_to_command() -> None:
    """Обратная связь переводится в команду с кортежем меток."""
    request = FeedbackRequest(
        rating=FeedbackRating.DOWN, reason="неточно", labels=["a", "b"]
    )
    command = request.to_command(AgentRunId(UUID(int=7)))

    assert command.rating is FeedbackRating.DOWN
    assert command.reason == "неточно"
    assert command.labels == ("a", "b")
    assert command.agent_run_id.value == UUID(int=7)


def test_feedback_request_rejects_unknown_rating() -> None:
    """Недопустимая оценка отклоняется валидацией."""
    with pytest.raises(ValidationError):
        FeedbackRequest(rating="maybe")
