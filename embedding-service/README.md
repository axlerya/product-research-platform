# embedding-service

Единый inference-слой для генерации **dense + sparse** эмбеддингов моделью
`BAAI/bge-m3`. Модель грузится в память один раз на процесс и обслуживает два
транспорта:

- **асинхронный** конвейер эмбеддинга документов через RabbitMQ + FastStream
  (команда → событие-результат, потребитель не блокируется);
- **синхронный** эмбеддинг поисковых запросов через gRPC (unary + batch,
  обязательный deadline).

Сервис — stateless: не хранит векторы, не ищет, не содержит бизнес-логики
каталога. Архитектура — строго Clean Architecture, разработка — по TDD.

## Стек

Python 3.12+, `uv`, `ruff` (line-length 80), `import-linter` (правило
зависимостей как исполняемый инвариант), `grpcio` (grpc.aio) + `grpc.health.v1`,
`FastStream[rabbit]`, `FlagEmbedding` `BGEM3FlagModel` за портом (опц. extra
`embedding`), `torch` (cpu/cuda), Pydantic v2 + pydantic-settings, OpenTelemetry
+ prometheus-client, Typer.

## Структура (Clean Architecture)

```
embedding_service/
├── domain/          # VO + чистые проверки (только stdlib)
├── application/     # use cases + порты (Protocol) + DTO
├── infrastructure/  # реализации портов (BGE-M3, батчер, config, obs)
└── presentation/    # FastStream, gRPC, ops-ASGI, Typer CLI
```

## Разработка

```bash
uv sync                 # рантайм + dev-зависимости (без extra "embedding")
uv run ruff check .     # линт
uv run ruff format --check .
uv run lint-imports     # правило зависимостей (import-linter)
uv run pytest -m "not integration and not slow and not nightly"
```

Реальная модель `BAAI/bge-m3` (~2.3ГБ) в CI не грузится — используется
детерминированный FAKE-провайдер (`EMBEDDING_PROVIDER_MODE=deterministic`).
Установка in-process эмбеддера: `uv sync --extra embedding`.

Конфигурация — переменными окружения с префиксом `EMBEDDING_` (см.
`.env.example`).

## Reranking (опционально, `BAAI/bge-reranker-v2-m3`)

Отдельная **полностью изолированная** функциональность: cross-encoder
переупорядочивает документы по релевантности запросу. Не затрагивает генерацию
dense/sparse эмбеддингов и модель BGE-M3.

- **Транспорт:** отдельный gRPC-сервис `reranker.v1.RerankerService` (метод
  `Rerank`) на том же порту `:50051`; отдельный proto-контракт.
- **Переключатель:** `RERANKER_ENABLED` (по умолчанию `false`). Выключен —
  сервис работает в прежнем режиме, `Rerank` → `UNIMPLEMENTED`.
- **Изоляция жизненного цикла:** сбой загрузки reranker **не роняет**
  embeddings — reranker переходит в `NOT_SERVING`, `Rerank` → `UNAVAILABLE`,
  остальной сервис продолжает работать (graceful degrade).
- **Настройки:** отдельный префикс `RERANKER_*` (модель, устройство,
  `MAX_BATCH_SIZE`, `INFERENCE_TIMEOUT_S`, `MAX_CONCURRENT_INFERENCES`, лимиты).
- **Health/readiness/метрики:** gRPC health по имени `reranker.v1.RerankerService`,
  HTTP `/reranker/ready`, метрики `reranker_*` в общем `/metrics`.
- **Установка модели:** `uv sync --extra reranking` (FAKE-режим
  `RERANKER_PROVIDER_MODE=deterministic` torch не требует).

```bash
# Включить reranker в FAKE-режиме (без весов):
RERANKER_ENABLED=true RERANKER_PROVIDER_MODE=deterministic \
  python -m embedding_service serve
```

## CLI

Точка входа — `python -m embedding_service` (Typer):

```bash
python -m embedding_service describe-model   # model_version / device / precision
python -m embedding_service warmup           # загрузить и прогреть модель
python -m embedding_service serve            # обе плоскости (composition root)
```

`serve` поднимает на одном event loop: gRPC-сервер запросов
(`EMBEDDING_GRPC_PORT`, по умолчанию `50051`), FastStream-консюмер команд
документов и ops-плоскость (`EMBEDDING_OPS_HTTP_PORT`, по умолчанию `8000`):
`/health`, `/ready`, `/metrics`.

## Запуск в Docker

Образы и compose лежат в `docker/` и `docker-compose.yml`. Профили выбирают
провайдер:

| Профиль | Провайдер | Назначение |
|---------|-----------|------------|
| `fake`  | `deterministic` | быстрый end-to-end smoke без torch и загрузки модели |
| `cpu`   | `bge_m3` на CPU | реальная BAAI/bge-m3, без GPU |
| `gpu`   | `bge_m3` на CUDA | реальная BAAI/bge-m3, нужен NVIDIA Container Toolkit |

```bash
# Быстрый smoke: RabbitMQ + сервис в FAKE-режиме.
docker compose --profile fake up --build

# Реальная модель на CPU (веса кэшируются в volume hf-cache).
docker compose --profile cpu up --build

# Реальная модель на GPU (требует --gpus, см. deploy.resources в compose).
docker compose --profile gpu up --build
```

После старта:

- gRPC — `localhost:50051` (рефлексия включена; `grpc.health.v1` для проб);
- ops — `http://localhost:8000/ready` (503 пока модель не прогрета → 200),
  `http://localhost:8000/health`, `http://localhost:8000/metrics`;
- RabbitMQ management — `http://localhost:15672` (`guest`/`guest`).

Образы собираются отдельно от compose:

```bash
docker build -f docker/Dockerfile.cpu -t embedding-service:cpu .
docker build -f docker/Dockerfile.gpu -t embedding-service:gpu .
```

Контейнер запускается непривилегированным пользователем, PID 1 — `python`
(корректный graceful-дренаж по `SIGTERM`), готовность отдаёт `HEALTHCHECK` через
`/ready`. Веса HuggingFace кэшируются в `HF_HOME=/app/.cache/huggingface`
(volume `hf-cache`).
