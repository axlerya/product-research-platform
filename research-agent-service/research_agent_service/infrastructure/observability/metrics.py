"""Метрики Prometheus в изолированном CollectorRegistry."""

from collections.abc import Iterable
from dataclasses import dataclass

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from research_agent_service.application.dto.answer import AnswerQueryResult

METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST


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


class MetricsRecorder:
    """Запись метрик пути запроса и отдача /metrics из своего реестра."""

    def __init__(
        self,
        *,
        registry: CollectorRegistry,
        metrics: Metrics,
        model: str,
    ) -> None:
        self._registry = registry
        self._metrics = metrics
        self._model = model

    @classmethod
    def create(cls, *, model: str = "agent") -> "MetricsRecorder":
        """Строит рекордер с собственным реестром."""
        registry = CollectorRegistry()
        return cls(
            registry=registry,
            metrics=build_metrics(registry),
            model=model,
        )

    def run_started(self) -> None:
        """Отмечает начало прогона (gauge активных прогонов)."""
        self._metrics.active_runs.inc()

    def run_finished(self) -> None:
        """Отмечает завершение прогона."""
        self._metrics.active_runs.dec()

    def rate_limited(self) -> None:
        """Считает отклонение по rate limit."""
        self._metrics.rate_limited_total.inc()

    def observe_query(
        self, result: AnswerQueryResult, *, latency_s: float
    ) -> None:
        """Пишет латентность, токены, инструменты и деградации прогона."""
        self._metrics.query_seconds.labels(status=result.status.value).observe(
            latency_s
        )
        self._observe_tokens(result)
        for tool in result.used_tools:
            self._metrics.tool_calls_total.labels(
                tool=tool.value, status="used"
            ).inc()
        for degradation in result.degradations:
            self._metrics.degradations_total.labels(
                dependency=degradation.dependency
            ).inc()

    def _observe_tokens(self, result: AnswerQueryResult) -> None:
        pairs: Iterable[tuple[str, int]] = (
            ("prompt", result.usage.prompt_tokens),
            ("completion", result.usage.completion_tokens),
        )
        for kind, amount in pairs:
            self._metrics.llm_tokens_total.labels(
                model=self._model, kind=kind
            ).inc(amount)

    def render(self) -> bytes:
        """Сериализует реестр в текстовый формат Prometheus."""
        return generate_latest(self._registry)
