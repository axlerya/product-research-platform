"""Метрики Prometheus (§10.2).

Собираются в переданный ``CollectorRegistry`` (без глобального состояния —
тестируется на свежем реестре).
"""

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


@dataclass(frozen=True, slots=True)
class Metrics:
    """Набор метрик сервиса (латентность/throughput/ресурсы/состояние)."""

    inference_seconds: Histogram
    queue_wait_seconds: Histogram
    batch_size: Histogram
    token_count: Histogram
    texts_total: Counter
    requests_total: Counter
    retries_total: Counter
    inference_errors_total: Counter
    oom_total: Counter
    dlq_total: Counter
    inflight: Gauge
    queue_depth: Gauge
    model_info: Gauge
    rss_bytes: Gauge
    vram_bytes: Gauge
    gpu_utilization: Gauge


def build_metrics(registry: CollectorRegistry) -> Metrics:
    """Регистрирует и возвращает метрики в заданном реестре."""
    return Metrics(
        inference_seconds=Histogram(
            "embedding_inference_seconds",
            "Латентность одного encode-батча",
            ["kind"],
            registry=registry,
        ),
        queue_wait_seconds=Histogram(
            "embedding_queue_wait_seconds",
            "Ожидание в полосе до инференса",
            ["lane"],
            registry=registry,
        ),
        batch_size=Histogram(
            "embedding_batch_size",
            "Размер скоалессированного батча",
            ["lane"],
            registry=registry,
        ),
        token_count=Histogram(
            "embedding_token_count",
            "Число токенов на текст",
            registry=registry,
        ),
        texts_total=Counter(
            "embedding_texts_total",
            "Обработано текстов",
            ["kind"],
            registry=registry,
        ),
        requests_total=Counter(
            "embedding_requests_total",
            "Обработано запросов/команд",
            ["transport", "kind", "status"],
            registry=registry,
        ),
        retries_total=Counter(
            "embedding_retries_total",
            "Транзиентные ретраи инференса",
            registry=registry,
        ),
        inference_errors_total=Counter(
            "embedding_inference_errors_total",
            "Ошибки инференса по типу",
            ["type"],
            registry=registry,
        ),
        oom_total=Counter(
            "embedding_oom_total",
            "Пойманные CUDA OOM",
            registry=registry,
        ),
        dlq_total=Counter(
            "embedding_dlq_total",
            "Команды, отправленные в parking DLQ",
            registry=registry,
        ),
        inflight=Gauge(
            "embedding_inflight",
            "Инференсов выполняется прямо сейчас",
            registry=registry,
        ),
        queue_depth=Gauge(
            "embedding_queue_depth",
            "Глубина полосы ожидания",
            ["lane"],
            registry=registry,
        ),
        model_info=Gauge(
            "embedding_model_info",
            "Информация о модели (value=1)",
            ["model_version", "device", "precision"],
            registry=registry,
        ),
        rss_bytes=Gauge(
            "embedding_rss_bytes",
            "RSS процесса",
            registry=registry,
        ),
        vram_bytes=Gauge(
            "embedding_vram_bytes",
            "Занятая VRAM",
            registry=registry,
        ),
        gpu_utilization=Gauge(
            "embedding_gpu_utilization",
            "Загрузка GPU",
            registry=registry,
        ),
    )
