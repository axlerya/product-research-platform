"""Порт ``IndexingMetrics`` — прикладные метрики свежести (§9.6).

Application не знает про Prometheus: он лишь сообщает, что произошло.
Реализация живёт в infrastructure, а по умолчанию подставляется no-op —
метрики не должны быть обязательным условием работы use case.
"""

from typing import Protocol


class IndexingMetrics(Protocol):
    """Счётчики применения результатов эмбеддинга."""

    def chunk_applied(self, *, applied: bool) -> None:
        """Чанк записан в Qdrant (``applied=False`` — пропущен как stale)."""
        ...

    def job_finished(self, *, latency_s: float, failed: bool) -> None:
        """Задание дошло до терминального статуса за ``latency_s`` секунд."""
        ...


class NullMetrics:
    """Заглушка: метрики выключены (тесты, CLI)."""

    def chunk_applied(self, *, applied: bool) -> None:
        return None

    def job_finished(self, *, latency_s: float, failed: bool) -> None:
        return None
