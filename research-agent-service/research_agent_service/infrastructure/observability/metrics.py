"""Метрики Prometheus в изолированном CollectorRegistry."""

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


@dataclass(frozen=True, slots=True)
class Metrics:
    """Набор метрик сервиса (метки — замкнутые enum'ы значений)."""

    query_seconds: Histogram
    tool_calls_total: Counter
    llm_tokens_total: Counter
    degradations_total: Counter
    rate_limited_total: Counter
    active_runs: Gauge


def build_metrics(registry: CollectorRegistry) -> Metrics:
    """Строит метрики в переданном (per-role) реестре."""
    return Metrics(
        query_seconds=Histogram(
            "research_agent_query_seconds",
            "Латентность POST /query",
            ["status"],
            registry=registry,
        ),
        tool_calls_total=Counter(
            "research_agent_tool_calls",
            "Вызовы инструментов",
            ["tool", "status"],
            registry=registry,
        ),
        llm_tokens_total=Counter(
            "research_agent_llm_tokens",
            "Токены LLM",
            ["model", "kind"],
            registry=registry,
        ),
        degradations_total=Counter(
            "research_agent_degradations",
            "Деградации зависимостей",
            ["dependency"],
            registry=registry,
        ),
        rate_limited_total=Counter(
            "research_agent_rate_limited",
            "Отклонения по rate limit",
            registry=registry,
        ),
        active_runs=Gauge(
            "research_agent_active_runs",
            "Активные прогоны агента",
            registry=registry,
        ),
    )
