"""Тесты доменной политики ограничений цикла агента."""

from dataclasses import FrozenInstanceError

import pytest

from research_agent_service.domain.policies import (
    DEFAULT_AGENT_LOOP_POLICY,
    AgentLoopPolicy,
)


def test_default_limits() -> None:
    """Значения политики по умолчанию согласованы с бюджетом прогона."""
    policy = AgentLoopPolicy()

    assert policy.max_steps == 6
    assert policy.max_tool_calls == 8
    assert policy.max_same_tool_calls == 2
    assert policy.token_budget == 60_000
    assert policy.wall_clock_budget_s == 25.0
    assert policy.finalize_reserve_s == 4.0


def test_allows_tool_call_within_limits() -> None:
    """В пределах всех лимитов — очередной вызов разрешён."""
    policy = AgentLoopPolicy()

    assert policy.allows_tool_call(
        step=1, tool_call_count=1, same_tool_calls=0, tokens_spent=0
    )


@pytest.mark.parametrize(
    ("step", "tool_call_count", "same_tool_calls", "tokens_spent"),
    [
        (6, 0, 0, 0),  # исчерпаны шаги
        (0, 8, 0, 0),  # исчерпаны вызовы
        (0, 0, 2, 0),  # исчерпан лимит одного инструмента
        (0, 0, 0, 60_000),  # исчерпан токен-бюджет
    ],
)
def test_allows_tool_call_blocks_at_each_limit(
    step: int,
    tool_call_count: int,
    same_tool_calls: int,
    tokens_spent: int,
) -> None:
    """При достижении любого лимита очередной вызов запрещён."""
    policy = AgentLoopPolicy()

    assert not policy.allows_tool_call(
        step=step,
        tool_call_count=tool_call_count,
        same_tool_calls=same_tool_calls,
        tokens_spent=tokens_spent,
    )


def test_clamp_deadline_uses_static_when_budget_is_ample() -> None:
    """Когда бюджета в достатке — берётся статический дедлайн вызова."""
    policy = AgentLoopPolicy()

    effective = policy.clamp_deadline(
        remaining_seconds=20.0, static_deadline_s=5.0
    )

    assert effective == 5.0


def test_clamp_deadline_reserves_finalize_tail() -> None:
    """Дедлайн урезается до остатка минус резерв на finalize."""
    policy = AgentLoopPolicy(finalize_reserve_s=4.0)

    effective = policy.clamp_deadline(
        remaining_seconds=6.0, static_deadline_s=5.0
    )

    assert effective == 2.0


def test_clamp_deadline_zero_when_budget_exhausted() -> None:
    """Если времени меньше резерва — вызов запускать нельзя (0.0)."""
    policy = AgentLoopPolicy(finalize_reserve_s=4.0)

    effective = policy.clamp_deadline(
        remaining_seconds=3.0, static_deadline_s=5.0
    )

    assert effective == 0.0


def test_policy_is_frozen() -> None:
    """Политика неизменяема."""
    policy = AgentLoopPolicy()

    with pytest.raises(FrozenInstanceError):
        policy.max_steps = 10


def test_default_singleton_is_policy() -> None:
    """Готовый экземпляр по умолчанию доступен для инъекции."""
    assert isinstance(DEFAULT_AGENT_LOOP_POLICY, AgentLoopPolicy)
