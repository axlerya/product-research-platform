"""Доменная политика ограничений цикла агента.

Лимиты одного прогона — это бизнес-правило, а не деталь фреймворка:
исполнитель (граф) лишь применяет их. Значения по умолчанию согласованы
так, что худший допустимый набор вызовов укладывается в бюджет времени.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentLoopPolicy:
    """Лимиты одного прогона агента.

    Attributes:
        max_steps: Максимум витков «планировщик ↔ инструменты».
        max_tool_calls: Максимум вызовов инструментов за прогон.
        max_same_tool_calls: Максимум вызовов одного инструмента (антицикл).
        token_budget: Суммарный бюджет токенов prompt+completion.
        wall_clock_budget_s: Жёсткий дедлайн прогона в секундах.
        llm_call_cap_s: Пер-вызовный потолок любого LLM-вызова.
        finalize_reserve_s: Резерв времени под финальную сборку ответа.
        retrieval_candidates: Сколько кандидатов брать из каждого prefetch.
        rerank_input_max: Усечение перед реранкером.
        final_top_k: Сколько товаров попадёт в контекст ответа.
    """

    max_steps: int = 6
    max_tool_calls: int = 8
    max_same_tool_calls: int = 2
    token_budget: int = 60_000
    wall_clock_budget_s: float = 25.0
    llm_call_cap_s: float = 8.0
    finalize_reserve_s: float = 4.0
    retrieval_candidates: int = 100
    rerank_input_max: int = 60
    final_top_k: int = 8

    def allows_tool_call(
        self,
        *,
        step: int,
        tool_call_count: int,
        same_tool_calls: int,
        tokens_spent: int,
    ) -> bool:
        """Разрешён ли ещё один вызов инструмента по счётным лимитам.

        Временной лимит проверяется отдельно через ``clamp_deadline`` —
        он требует часов и живёт в исполнителе.
        """
        return (
            step < self.max_steps
            and tool_call_count < self.max_tool_calls
            and same_tool_calls < self.max_same_tool_calls
            and tokens_spent < self.token_budget
        )

    def clamp_deadline(
        self, *, remaining_seconds: float, static_deadline_s: float
    ) -> float:
        """Урезает дедлайн вызова до остатка бюджета за вычетом резерва.

        Args:
            remaining_seconds: Остаток бюджета прогона.
            static_deadline_s: Статический дедлайн конкретного вызова.

        Returns:
            Эффективный дедлайн; ``0.0`` — времени на вызов нет, пора
            финализировать.
        """
        budget_left = remaining_seconds - self.finalize_reserve_s
        return max(0.0, min(static_deadline_s, budget_left))


DEFAULT_AGENT_LOOP_POLICY = AgentLoopPolicy()
