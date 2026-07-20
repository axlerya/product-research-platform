"""Метрики Prometheus reranker (изолированный набор).

Отдельный файл и отдельные имена ``reranker_*`` — не пересекается с
embedding-метриками (``metrics.py`` не тронут). Собирается в переданный
``CollectorRegistry`` (без глобального состояния — тестируется на свежем
реестре).
"""

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


@dataclass(frozen=True, slots=True)
class RerankerMetrics:
    """Набор метрик reranker (латентность/throughput/скор/состояние)."""

    inference_seconds: Histogram
    documents: Histogram
    batch_size: Histogram
    score: Histogram
    requests_total: Counter
    errors_total: Counter
    timeouts_total: Counter
    oom_total: Counter
    inflight: Gauge
    model_info: Gauge


def build_reranker_metrics(registry: CollectorRegistry) -> RerankerMetrics:
    """Регистрирует и возвращает метрики reranker в заданном реестре."""
    return RerankerMetrics(
        inference_seconds=Histogram(
            "reranker_inference_seconds",
            "Латентность одного compute-чанка reranker",
            registry=registry,
        ),
        documents=Histogram(
            "reranker_documents",
            "Число документов в rerank-запросе",
            registry=registry,
        ),
        batch_size=Histogram(
            "reranker_batch_size",
            "Размер чанка пар, отданного модели",
            registry=registry,
        ),
        score=Histogram(
            "reranker_score",
            "Распределение скоров релевантности",
            registry=registry,
        ),
        requests_total=Counter(
            "reranker_requests_total",
            "Обработано rerank-запросов",
            ["status"],
            registry=registry,
        ),
        errors_total=Counter(
            "reranker_errors_total",
            "Ошибки reranker по типу",
            ["type"],
            registry=registry,
        ),
        timeouts_total=Counter(
            "reranker_timeouts_total",
            "Пойманные таймауты инференса reranker",
            registry=registry,
        ),
        oom_total=Counter(
            "reranker_oom_total",
            "Пойманные CUDA OOM reranker",
            registry=registry,
        ),
        inflight=Gauge(
            "reranker_inflight",
            "Rerank-инференсов выполняется прямо сейчас",
            registry=registry,
        ),
        model_info=Gauge(
            "reranker_model_info",
            "Информация о reranker-модели (value=1)",
            ["model_version", "device", "precision"],
            registry=registry,
        ),
    )
