"""Тесты value objects прогона: TokenUsage, Degradation, RunError."""

from dataclasses import FrozenInstanceError

import pytest

from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import (
    ErrorCategory,
    ErrorCode,
    RunStage,
)
from research_agent_service.domain.value_objects.run_error import RunError
from research_agent_service.domain.value_objects.usage import TokenUsage


def test_token_usage_total_is_sum() -> None:
    """total — сумма prompt и completion токенов."""
    usage = TokenUsage(prompt_tokens=1200, completion_tokens=340)

    assert usage.total == 1540


def test_token_usage_is_frozen() -> None:
    """TokenUsage неизменяем."""
    usage = TokenUsage(prompt_tokens=1, completion_tokens=1)

    with pytest.raises(FrozenInstanceError):
        usage.prompt_tokens = 2


def test_degradation_holds_dependency_and_reason() -> None:
    """Degradation несёт отказавшую зависимость и причину."""
    degradation = Degradation(dependency="reranker", reason="unimplemented")

    assert degradation.dependency == "reranker"
    assert degradation.reason == "unimplemented"


def test_run_error_holds_structured_fields() -> None:
    """RunError несёт код, категорию, стадию и сообщение."""
    error = RunError(
        code=ErrorCode.CATALOG_UNAVAILABLE,
        category=ErrorCategory.UPSTREAM,
        stage=RunStage.PRICE_ANALYSIS,
        message="catalog analyze-prices недоступен",
    )

    assert error.code is ErrorCode.CATALOG_UNAVAILABLE
    assert error.category is ErrorCategory.UPSTREAM
    assert error.stage is RunStage.PRICE_ANALYSIS


def test_run_error_is_frozen() -> None:
    """RunError неизменяем."""
    error = RunError(
        code=ErrorCode.INTERNAL,
        category=ErrorCategory.INTERNAL,
        stage=RunStage.PLAN,
        message="x",
    )

    with pytest.raises(FrozenInstanceError):
        error.message = "y"
