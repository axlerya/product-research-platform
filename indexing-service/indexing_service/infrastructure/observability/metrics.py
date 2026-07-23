"""Прикладные метрики свежести read-model (§9.6).

Транспортные метрики даёт ``RabbitPrometheusMiddleware``; здесь — то, чего
она знать не может: сколько заданий висит без ответа, насколько отстала
публикация outbox и как долго товар идёт от события до векторов.

Коллекторы регистрируются в переданном ``CollectorRegistry`` — у каждой
роли он свой, глобальный REGISTRY не используем.
"""

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

# Задание может ждать embedding-service от секунд до десятков минут.
_LATENCY_BUCKETS = (1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600)


@dataclass(frozen=True, slots=True)
class PrometheusMetrics:
    """Реализация ``IndexingMetrics`` поверх prometheus_client."""

    applied: Counter
    latency: Histogram

    def chunk_applied(self, *, applied: bool) -> None:
        self.applied.labels(outcome="applied" if applied else "stale").inc()

    def job_finished(self, *, latency_s: float, failed: bool) -> None:
        self.latency.labels(
            outcome="failed" if failed else "done"
        ).observe(latency_s)


def build_metrics(registry: CollectorRegistry) -> PrometheusMetrics:
    """Регистрирует счётчики применения результата."""
    return PrometheusMetrics(
        applied=Counter(
            "embeddings_applied_total",
            "Чанков, применённых к Qdrant",
            labelnames=("outcome",),
            registry=registry,
        ),
        latency=Histogram(
            "indexing_job_latency_seconds",
            "Время от постановки задания до его завершения",
            labelnames=("outcome",),
            buckets=_LATENCY_BUCKETS,
            registry=registry,
        ),
    )


class BacklogGauges:
    """Замеряет отставание конвейера прямо из Postgres.

    Gauge'и такого рода нельзя инкрементировать из кода: источник истины —
    таблицы, а процессов несколько. Поэтому значения переснимаются опросом
    (relay всё равно опрашивает outbox в цикле).
    """

    _AWAITING_SQL = text(
        "SELECT count(*) FROM indexing_jobs "
        "WHERE status IN ('pending', 'awaiting', 'partially_failed')"
    )
    _LAG_SQL = text(
        "SELECT COALESCE("
        "  EXTRACT(EPOCH FROM now() - min(occurred_at)), 0) "
        "FROM outbox "
        "WHERE published_at IS NULL AND failed_at IS NULL"
    )
    _QUARANTINE_SQL = text(
        "SELECT count(*) FROM outbox WHERE failed_at IS NOT NULL"
    )

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        registry: CollectorRegistry,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._awaiting = Gauge(
            "indexing_jobs_awaiting",
            "Заданий, ожидающих векторы",
            registry=registry,
        )
        self._lag = Gauge(
            "outbox_lag_seconds",
            "Возраст самой старой неопубликованной команды",
            registry=registry,
        )
        self._quarantined = Gauge(
            "outbox_quarantined",
            "Строк outbox в карантине (исчерпали попытки)",
            registry=registry,
        )

    async def refresh(self) -> None:
        """Переснимает значения gauge'ей из БД."""
        async with self._sessionmaker() as session:
            self._awaiting.set(await session.scalar(self._AWAITING_SQL) or 0)
            self._lag.set(float(await session.scalar(self._LAG_SQL) or 0))
            self._quarantined.set(
                await session.scalar(self._QUARANTINE_SQL) or 0
            )
