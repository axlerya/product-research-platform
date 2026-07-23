# indexing-service

Построитель поисковой read-model для платформы исследования товаров:
потребляет события об изменениях каталога из RabbitMQ (FastStream), формирует
поисковые документы и поддерживает коллекцию **Qdrant** в актуальном
состоянии. Векторы **не считает сам** — заказывает их у `embedding-service`
командой и применяет пришедший результат. Изменение цены/остатка/метрик
обновляет payload **без пересчёта эмбеддингов**.

> Архитектура и ключевые решения — в [`ARCHITECTURE.md`](./ARCHITECTURE.md).
> Правила разработки (Clean Architecture, TDD, ветки/коммиты) — в
> [`AGENTS.md`](./AGENTS.md).

## Как устроен конвейер

Две фазы, разведённые по разным exchange — никакого RPC и ожидания ответа:

```
catalog.events ──▶ consumer ──┬──▶ Qdrant (карточка товара, без векторов)
                              └──▶ Postgres: indexing_jobs + outbox  (одна транзакция)
                                            │
                                     relay  ▼
                                   embedding.jobs ──▶ embedding-service
                                                            │
                        Qdrant ◀── result-consumer ◀── embedding.events
                     (векторы + водяные знаки)
```

Коммерческие изменения, дедуп по тексту и удаление идут прямым путём в
Qdrant, мимо `embedding-service`.

## Слои (Clean Architecture)

```
domain/          # чистые бизнес-правила проекции (только stdlib)
application/     # use cases, порты, DTO (зависит только от domain)
infrastructure/  # Qdrant, Postgres, RabbitMQ, HTTP-клиент catalog, config
presentation/    # FastStream-консюмеры, relay, Typer CLI
```

Правило зависимостей — исполняемый инвариант (`import-linter`).

## Требования

- Python 3.12+, [`uv`](https://docs.astral.sh/uv/)
- Docker + Docker Compose (для запуска стека и integration-тестов)

## Установка и тесты

```bash
uv sync                                  # зависимости (рантайм + dev)

uv run pytest tests/unit tests/contract  # без Docker
uv run pytest -m integration             # нужен Docker (testcontainers)
uv run ruff check .                      # линт (80 колонок, Google style)
uv run lint-imports                      # правило зависимостей слоёв
```

Модели и torch в зависимостях нет: за векторы отвечает `embedding-service`.

## Запуск стека (Docker Compose)

Compose поднимает Qdrant, Postgres, RabbitMQ и три роли одного образа:
`consumer` (каталог), `relay` (outbox → брокер) и `result-consumer`
(результаты эмбеддинга). Миграции накатывает только `consumer`
(`RUN_MIGRATIONS=1`).

```bash
cd docker
docker compose up --build
```

Порты HTTP: `8000` — консюмер каталога, `8001` — консюмер результатов; у
обоих `GET /health` и `GET /metrics`.

Чтобы прогнать конвейер целиком без соседнего сервиса, поднимите заглушку —
она отвечает на команды детерминированными векторами:

```bash
docker compose --profile fake-embedding up fake-embedding
```

Batch-операции (профили):

```bash
docker compose run --rm reconcile                    # сверка каталог ↔ Qdrant
docker compose --profile reindex up reindex          # завести эпоху reindex
docker compose --profile reindex up reindex-swap     # переключить alias
```

### Интеграция с catalog-service

Консюмер слушает exchange `catalog.events`. Чтобы события пошли,
`catalog-service` должен публиковать в **тот же** RabbitMQ (общий
брокер/сеть). Gap-repair, reindex и reconcile ходят в catalog по REST
(`INDEXING_CATALOG_BASE_URL`).

## CLI

```bash
python -m indexing_service --help
python -m indexing_service provision                       # коллекция + alias
python -m indexing_service reconcile                       # сверка (§9)
python -m indexing_service reindex --target products_v2    # завести эпоху (§8)
python -m indexing_service reindex-swap --target products_v2  # переключить alias
python -m indexing_service replay-dlq                      # переотправить DLQ
```

`reindex` только ставит задания — векторы считает `embedding-service`.
Переключать alias можно, когда эпоха готова; `reindex-swap` проверяет это
сам и выходит с кодом `1`, если ещё рано. Порог `--min-ready` позволяет не
ждать безнадёжно отставших.

## Конфигурация (переменные окружения, префикс `INDEXING_`)

Полный список — в [`.env.example`](./.env.example). Ключевые:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `INDEXING_RABBITMQ_DSN` | `amqp://guest:guest@localhost:5672/` | брокер событий |
| `INDEXING_DATABASE_URL` | `postgresql+asyncpg://indexing:indexing@localhost:5432/indexing` | jobs + outbox |
| `INDEXING_QDRANT_URL` | `http://localhost:6333` | Qdrant |
| `INDEXING_CATALOG_BASE_URL` | `http://localhost:8000` | catalog REST |
| `INDEXING_COLLECTION_ALIAS` | `products` | alias коллекции (читатели) |
| `INDEXING_EMBEDDING_DIM` | `1024` | размерность dense |
| `INDEXING_EXPECTED_MODEL` | пусто | закрепить модель; пусто — доверяем текущей |
| `INDEXING_MAX_TEXTS` | `32` | лимит items в одной команде |
| `INDEXING_MAX_ITEM_ATTEMPTS` | `5` | попыток на чанк до DLQ |
| `INDEXING_SOURCE_MODE` | `hybrid` | `event` \| `hybrid` \| `fetch` |
| `INDEXING_MAX_ATTEMPTS` | `5` | ретраи сообщения до DLQ |
| `INDEXING_RETRY_TTL_MS` | `30000` | backoff retry-очереди |

## Статус и ограничения

**Реализовано и покрыто тестами:**

- Все доменные правила, идемпотентная обработка событий, transactional
  outbox + relay, консюмер результатов с item-level ретраями и rechunk,
  batch use cases reindex/reconcile на job-модели, CLI — **юнит-тесты +
  CDC-контракт** (golden-примеры + JSON Schema).
- **Integration-тесты (`testcontainers`)**: реальные Qdrant, Postgres и
  RabbitMQ — атомарность job+outbox, relay (SKIP LOCKED, backoff,
  карантин), e2e горячего пути и плеча результатов.
- **Наблюдаемость (§10)**: `/health` + `/metrics` (Prometheus); distributed
  tracing (OpenTelemetry, opt-in через `INDEXING_OTLP_ENDPOINT`).

**Не реализовано (следующие шаги):** прикладные метрики свежести
(`indexing_job_latency`, `indexing_jobs_awaiting`, `outbox_lag_seconds`) и
сверка зависших jobs — шаг 8 плана рефакторинга; `/ready` с отдельной
проверкой Qdrant.
