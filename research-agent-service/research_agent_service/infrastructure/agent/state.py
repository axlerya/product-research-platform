"""Состояние графа агента (LangGraph).

Списки-аккумуляторы имеют reducer operator.add — вклады узлов складываются
по ходу цикла. run_id и deadline_at задаются один раз в стартовом состоянии.
"""

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from research_agent_service.domain.entities.tool_call import ToolCall
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import ToolName
from research_agent_service.domain.value_objects.identifiers import AgentRunId


class AgentState(TypedDict):
    """Разделяемое состояние узлов графа агента."""

    messages: Annotated[list[BaseMessage], add_messages]
    steps: Annotated[int, operator.add]
    tool_call_total: Annotated[int, operator.add]
    tool_calls: Annotated[list[ToolCall], operator.add]
    citations: Annotated[list[Citation], operator.add]
    product_refs: Annotated[list[str], operator.add]
    web_refs: Annotated[list[str], operator.add]
    price_refs: Annotated[list[str], operator.add]
    degradations: Annotated[list[Degradation], operator.add]
    used_tools: Annotated[list[ToolName], operator.add]
    prompt_tokens: Annotated[int, operator.add]
    completion_tokens: Annotated[int, operator.add]
    run_id: AgentRunId
    deadline_at: float
