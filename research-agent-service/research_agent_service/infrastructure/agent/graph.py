"""Граф агента: цикл LLM ↔ инструменты в пределах лимитов политики.

Узел agent зовёт модель; пока в бюджете (шаги, число вызовов, дедлайн) —
с инструментами, иначе — без них (форсируем финальный ответ). Узел tools
исполняет вызовы через ToolExecutor и складывает provenance/деградации в
состояние. Незнакомое имя инструмента и превышение лимита повторов одного
инструмента исполнения не получают — модель видит это как наблюдение.
"""

import json
from collections import Counter
from collections.abc import Callable
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.graph import END, START, StateGraph

from research_agent_service.domain.policies import AgentLoopPolicy
from research_agent_service.infrastructure.agent.executor import ToolExecutor
from research_agent_service.infrastructure.agent.state import AgentState
from research_agent_service.infrastructure.agent.tools import (
    build_tool_specs,
    resolve_tool,
)

_AGENT = "agent"
_TOOLS = "tools"


def build_agent_graph(
    *,
    model: Any,
    executor: ToolExecutor,
    policy: AgentLoopPolicy,
    monotonic: Callable[[], float],
) -> Any:
    """Компилирует граф агента с внедрёнными моделью и исполнителем."""
    model_with_tools = model.bind_tools(build_tool_specs())

    async def agent_node(state: AgentState) -> dict[str, Any]:
        within_budget = (
            state["steps"] < policy.max_steps
            and state["tool_call_total"] < policy.max_tool_calls
            and monotonic() < state["deadline_at"]
        )
        active = model_with_tools if within_budget else model
        response = await active.ainvoke(state["messages"])
        usage = response.usage_metadata or {}
        return {
            "messages": [response],
            "steps": 1,
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
        }

    async def tools_node(state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        counts: Counter[Any] = Counter(state["used_tools"])
        acc = _Accumulator()
        for call in state["messages"][-1].tool_calls:
            tool = resolve_tool(call["name"])
            if tool is None:
                acc.messages.append(_error_message(call, "unknown_tool"))
                continue
            if counts[tool] >= policy.max_same_tool_calls:
                acc.messages.append(_error_message(call, "tool_repeat_limit"))
                continue
            counts[tool] += 1
            executed = await executor.execute(
                tool, call["args"], step_index=state["steps"], run_id=run_id
            )
            acc.absorb(executed, call)
        return acc.as_update()

    def route_after_agent(state: AgentState) -> str:
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return _TOOLS
        return END

    graph = StateGraph(AgentState)
    graph.add_node(_AGENT, agent_node)
    graph.add_node(_TOOLS, tools_node)
    graph.add_edge(START, _AGENT)
    graph.add_conditional_edges(_AGENT, route_after_agent, [_TOOLS, END])
    graph.add_edge(_TOOLS, _AGENT)
    return graph.compile()


class _Accumulator:
    """Собирает вклад узла tools в состояние за один проход."""

    def __init__(self) -> None:
        self.messages: list[ToolMessage] = []
        self.executed = 0
        self.calls: list[Any] = []
        self.citations: list[Any] = []
        self.degradations: list[Any] = []
        self.product_refs: list[str] = []
        self.web_refs: list[str] = []
        self.price_refs: list[str] = []
        self.used_tools: list[Any] = []

    def absorb(self, executed: Any, call: dict[str, Any]) -> None:
        self.executed += 1
        self.messages.append(
            ToolMessage(
                content=json.dumps(executed.observation, ensure_ascii=False),
                tool_call_id=call["id"],
                name=call["name"],
            )
        )
        self.calls.append(executed.tool_call)
        self.citations.extend(executed.citations)
        self.degradations.extend(executed.degradations)
        self.product_refs.extend(executed.product_refs)
        self.web_refs.extend(executed.web_refs)
        self.price_refs.extend(executed.price_refs)
        self.used_tools.append(executed.tool)

    def as_update(self) -> dict[str, Any]:
        return {
            "messages": self.messages,
            "tool_call_total": self.executed,
            "tool_calls": self.calls,
            "citations": self.citations,
            "degradations": self.degradations,
            "product_refs": self.product_refs,
            "web_refs": self.web_refs,
            "price_refs": self.price_refs,
            "used_tools": self.used_tools,
        }


def _error_message(call: dict[str, Any], error: str) -> ToolMessage:
    return ToolMessage(
        content=json.dumps({"error": error}, ensure_ascii=False),
        tool_call_id=call["id"],
        name=call["name"],
    )
