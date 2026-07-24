"""Тесты LangGraphOrchestrator и графа на фейковой модели и исполнителе."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from langchain_core.messages import AIMessage

from research_agent_service.domain.entities.tool_call import ToolCall
from research_agent_service.domain.policies import DEFAULT_AGENT_LOOP_POLICY
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import (
    CitationType,
    Confidence,
    ToolCallStatus,
    ToolName,
)
from research_agent_service.domain.value_objects.identifiers import (
    AgentRunId,
    ToolCallId,
)
from research_agent_service.domain.value_objects.query import Query
from research_agent_service.infrastructure.agent.executor import ExecutedTool
from research_agent_service.infrastructure.agent.orchestrator import (
    LangGraphOrchestrator,
    _confidence,
    _text,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_RUN = AgentRunId(UUID(int=1))


class _FakeModel:
    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)
        self.bound: object = None

    def bind_tools(self, tools: object) -> "_FakeModel":
        self.bound = tools
        return self

    async def ainvoke(self, messages: object) -> AIMessage:
        return self._responses.pop(0)


class _FakeExecutor:
    def __init__(self, result: ExecutedTool) -> None:
        self._result = result
        self.calls: list[tuple[ToolName, dict, AgentRunId]] = []

    async def execute(
        self,
        tool: ToolName,
        args: dict,
        *,
        step_index: int,
        run_id: AgentRunId,
    ) -> ExecutedTool:
        self.calls.append((tool, args, run_id))
        return self._result


class _FakeIds:
    def new_uuid7(self) -> UUID:
        return UUID(int=1)


def _rag_executed(*, degrade: bool = False) -> ExecutedTool:
    citation = Citation(
        source_type=CitationType.PRODUCT,
        ref="SKU-1",
        title="Наушники",
        snippet="s",
        position=0,
        retrieved_at=_NOW,
        score=Decimal("0.9"),
    )
    tool_call = ToolCall(
        id=ToolCallId(UUID(int=99)),
        agent_run_id=_RUN,
        step_index=0,
        tool=ToolName.PRODUCT_CATALOG_RAG,
        status=ToolCallStatus.OK,
        started_at=_NOW,
        finished_at=_NOW,
        latency_ms=10,
    )
    return ExecutedTool(
        tool=ToolName.PRODUCT_CATALOG_RAG,
        observation={"products": [{"sku": "SKU-1"}]},
        tool_call=tool_call,
        citations=(citation,),
        product_refs=("SKU-1",),
        degradations=(
            (Degradation("reranker", "unavailable"),) if degrade else ()
        ),
    )


def _rag_call(call_id: str = "c1", name: str = "product_catalog_rag") -> dict:
    return {"name": name, "args": {"query": "наушники"}, "id": call_id}


def _ai(content: str = "", *, tool_calls: list | None = None) -> AIMessage:
    return AIMessage(
        content=content,
        tool_calls=tool_calls or [],
        usage_metadata={
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        },
    )


def _orchestrator(
    model: _FakeModel,
    executor: _FakeExecutor,
    *,
    policy=DEFAULT_AGENT_LOOP_POLICY,
    monotonic=None,
) -> LangGraphOrchestrator:
    return LangGraphOrchestrator(
        model=model,
        executor=executor,
        id_generator=_FakeIds(),
        policy=policy,
        monotonic=monotonic or (lambda: 0.0),
    )


async def _run(orchestrator: LangGraphOrchestrator) -> object:
    return await orchestrator.run(
        Query(text="найди наушники"), (), deadline_s=25.0
    )


async def test_tool_then_final_answer() -> None:
    """Модель зовёт инструмент, затем даёт финальный ответ с источниками."""
    model = _FakeModel([_ai(tool_calls=[_rag_call()]), _ai("итог")])
    executor = _FakeExecutor(_rag_executed())

    outcome = await _run(_orchestrator(model, executor))

    assert outcome.answer == "итог"
    assert outcome.used_tools == (ToolName.PRODUCT_CATALOG_RAG,)
    assert outcome.retrieved_refs == ("SKU-1",)
    assert len(outcome.citations) == 1
    assert outcome.confidence is Confidence.HIGH
    assert outcome.loop_steps == 2
    assert outcome.usage.prompt_tokens == 20
    assert outcome.usage.completion_tokens == 10
    assert executor.calls[0][2] == _RUN


async def test_final_without_tools_is_low_confidence() -> None:
    """Ответ без инструментов → нет источников → LOW."""
    model = _FakeModel([_ai("сразу ответ")])
    outcome = await _run(_orchestrator(model, _FakeExecutor(_rag_executed())))

    assert outcome.answer == "сразу ответ"
    assert outcome.used_tools == ()
    assert outcome.citations == ()
    assert outcome.confidence is Confidence.LOW
    assert outcome.loop_steps == 1


async def test_max_steps_forces_finalize() -> None:
    """При исчерпании шагов последний вызов модели идёт без инструментов."""
    policy = DEFAULT_AGENT_LOOP_POLICY.__class__(max_steps=1)
    model = _FakeModel([_ai(tool_calls=[_rag_call()]), _ai("вынужденный итог")])
    executor = _FakeExecutor(_rag_executed())

    outcome = await _run(_orchestrator(model, executor, policy=policy))

    assert outcome.answer == "вынужденный итог"
    assert len(executor.calls) == 1
    assert outcome.loop_steps == 2


async def test_deadline_forces_finalize() -> None:
    """Просроченный дедлайн → следующий вызов идёт без инструментов."""
    times = iter([0.0, 0.0, 100.0])
    model = _FakeModel([_ai(tool_calls=[_rag_call()]), _ai("по дедлайну")])
    executor = _FakeExecutor(_rag_executed())

    orchestrator = _orchestrator(model, executor, monotonic=lambda: next(times))
    outcome = await orchestrator.run(Query(text="q"), (), deadline_s=5.0)

    assert outcome.answer == "по дедлайну"
    assert len(executor.calls) == 1


async def test_unknown_tool_is_not_executed() -> None:
    """Незнакомое имя инструмента не исполняется."""
    model = _FakeModel(
        [
            _ai(tool_calls=[_rag_call(name="drop_table")]),
            _ai("ответ"),
        ]
    )
    executor = _FakeExecutor(_rag_executed())

    outcome = await _run(_orchestrator(model, executor))

    assert executor.calls == []
    assert outcome.tool_calls == ()
    assert outcome.citations == ()


async def test_same_tool_repeat_limit() -> None:
    """Свыше лимита повторов одного инструмента вызовы пропускаются."""
    calls = [
        _rag_call("a"),
        _rag_call("b"),
        _rag_call("c"),
    ]
    model = _FakeModel([_ai(tool_calls=calls), _ai("итог")])
    executor = _FakeExecutor(_rag_executed())

    outcome = await _run(_orchestrator(model, executor))

    assert len(executor.calls) == 2
    assert outcome.used_tools == (ToolName.PRODUCT_CATALOG_RAG,)


async def test_degradations_yield_medium_confidence() -> None:
    """Источники с деградациями → MEDIUM; деградации дедуплицированы."""
    model = _FakeModel([_ai(tool_calls=[_rag_call()]), _ai("итог")])
    executor = _FakeExecutor(_rag_executed(degrade=True))

    outcome = await _run(_orchestrator(model, executor))

    assert outcome.confidence is Confidence.MEDIUM
    assert outcome.degradations == (Degradation("reranker", "unavailable"),)


def test_text_handles_str_list_and_other() -> None:
    """_text: строка как есть, список текст-частей склеивается, иначе str()."""
    assert _text("готово") == "готово"
    assert (
        _text([{"type": "text", "text": "а"}, {"type": "text", "text": "б"}])
        == "аб"
    )
    assert _text(None) == "None"


def test_confidence_levels() -> None:
    """LOW без источников, HIGH с источниками без деградаций."""
    citation = Citation(
        source_type=CitationType.WEB,
        ref="https://x",
        title="t",
        snippet="s",
        position=0,
        retrieved_at=_NOW,
    )
    assert _confidence((), ()) is Confidence.LOW
    assert _confidence((citation,), ()) is Confidence.HIGH
