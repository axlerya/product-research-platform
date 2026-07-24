"""Тесты доменных enum-словарей агента."""

from enum import StrEnum

import pytest

from research_agent_service.domain.value_objects.enums import (
    CitationType,
    Confidence,
    ErrorCategory,
    ErrorCode,
    FeedbackRating,
    MessageRole,
    RunStage,
    RunStatus,
    ToolCallStatus,
    ToolName,
)

ALL_ENUMS = [
    CitationType,
    Confidence,
    ErrorCategory,
    ErrorCode,
    FeedbackRating,
    MessageRole,
    RunStage,
    RunStatus,
    ToolCallStatus,
    ToolName,
]


@pytest.mark.parametrize("enum_type", ALL_ENUMS)
def test_is_str_enum(enum_type: type) -> None:
    """Все словари — StrEnum: члены сериализуются как строки на границах."""
    assert issubclass(enum_type, StrEnum)


def test_tool_name_is_closed_allowlist() -> None:
    """ToolName — ровно три обязательных инструмента, ничего лишнего."""
    assert {tool.value for tool in ToolName} == {
        "product_catalog_rag",
        "price_analysis",
        "web_search",
    }


def test_str_enum_member_equals_its_value() -> None:
    """Член StrEnum равен своей строке."""
    assert ToolName.WEB_SEARCH == "web_search"
    assert MessageRole.ASSISTANT == "assistant"


def test_run_status_covers_lifecycle() -> None:
    """RunStatus покрывает весь жизненный цикл прогона."""
    assert {status.value for status in RunStatus} == {
        "pending",
        "running",
        "completed",
        "degraded",
        "failed",
    }


def test_feedback_rating_is_binary() -> None:
    """Обратная связь — бинарная (up/down)."""
    assert {rating.value for rating in FeedbackRating} == {"up", "down"}


def test_citation_types_match_tool_sources() -> None:
    """Типы источников соответствуют инструментам, порождающим факты."""
    assert {source.value for source in CitationType} == {
        "product",
        "price_analysis",
        "web",
    }
