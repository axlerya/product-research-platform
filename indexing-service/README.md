# indexing-service

Построитель поисковой read-model для платформы исследования товаров:
потребляет события об изменениях каталога из RabbitMQ (FastStream), формирует
поисковые документы, считает **dense + sparse** эмбеддинги через **BGE-M3** и
поддерживает коллекцию **Qdrant** в актуальном состоянии. Изменение
цены/остатка/метрик обновляет payload **без пересоздания эмбеддингов**.

> Архитектура и ключевые решения — в [`ARCHITECTURE.md`](./ARCHITECTURE.md).
> Правила разработки (Clean Architecture, TDD, ветки/коммиты) — в
> [`AGENTS.md`](./AGENTS.md).

## Слои (Clean Architecture)

```
domain/          # чистые бизнес-правила проекции (только stdlib)
application/     # use cases, порты, DTO (зависит только от domain)
infrastructure/  # Qdrant, BGE-M3, HTTP-клиент catalog, config
presentation/    # FastStream-консюмер, Typer CLI
```

Правило зависимостей — исполняемый инвариант (`import-linter`).

## Требования

- Python 3.12+, [`uv`](https://docs.astral.sh/uv/)
- Docker + Docker Compose (для запуска стека)

## Установка и тесты

```bash
uv sync                      # зависимости (рантайм + dev; без тяжёлого эмбеддера)

uv run pytest                # все юнит-тесты (без Docker)
uv run ruff check .          # линт (80 колонок, Google style)
uv run lint-imports          # правило зависимостей слоёв
```

Тяжёлый in-process эмбеддер (BGE-M3 / torch) — опциональный extra:

```bash
uv sync --extra embedding    # ставит FlagEmbedding (~2.3ГБ модель тянется при первом запуске)
```

## Запуск стека (Docker Compose)

Compose поднимает Qdrant + RabbitMQ + консюмер. По умолчанию — **FAKE-режим
эмбеддера** (детерминированный хэш, `INDEXING_EMBEDDING_DIM=8`), чтобы конвейер
работал без загрузки BGE-M3 (удобно для smoke/CI).

```bash
cd docker
docker compose up --build          # qdrant + rabbitmq + consumer
```

Консюмер поднимает HTTP-порт `8000` (один процесс, uvicorn): `GET /health`
(пинг брокера → 204) и `GET /metrics` (Prometheus, метрики FastStream).

Batch-операции (профили):

```bash
docker compose run --rm reconcile                       # сверка каталог ↔ Qdrant
docker compose --profile reindex up reindex --build     # полная переиндексация + свап alias
```

### Продакшен-режим (BGE-M3)

Соберите образ с extra `embedding` и включите LOCAL-режим:

```yaml
# docker-compose override
environment:
  INDEXING_EMBEDDING_MODE: local
  INDEXING_EMBEDDING_MODEL: BAAI/bge-m3
  INDEXING_EMBEDDING_DIM: "1024"
```

### Интеграция с catalog-service

Консюмер слушает exchange `catalog.events`. Чтобы события пошли, `catalog-service`
должен публиковать в **тот же** RabbitMQ (общий брокер/сеть). Gap-repair,
reindex и reconcile ходят в catalog по REST (`INDEXING_CATALOG_BASE_URL`).

## CLI

```bash
python -m indexing_service --help
python -m indexing_service provision                 # создать коллекцию + alias
python -m indexing_service reconcile                 # сверка и починка дрейфа (§9)
python -m indexing_service reindex --target products_bge_m3_v2   # переиндексация (§8)
```

## Конфигурация (переменные окружения, префикс `INDEXING_`)

Полный список — в [`.env.example`](./.env.example). Ключевые:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `INDEXING_RABBITMQ_DSN` | `amqp://guest:guest@localhost:5672/` | брокер событий |
| `INDEXING_QDRANT_URL` | `http://localhost:6333` | Qdrant |
| `INDEXING_CATALOG_BASE_URL` | `http://localhost:8000` | catalog REST |
| `INDEXING_COLLECTION_ALIAS` | `products` | alias коллекции (читатели) |
| `INDEXING_EMBEDDING_MODE` | `local` | `local` \| `remote` \| `fake` |
| `INDEXING_EMBEDDING_DIM` | `1024` | размерность dense |
| `INDEXING_SOURCE_MODE` | `hybrid` | `event` \| `hybrid` \| `fetch` |
| `INDEXING_MAX_ATTEMPTS` | `5` | ретраи до DLQ |
| `INDEXING_RETRY_TTL_MS` | `30000` | backoff retry-очереди |

## Статус и ограничения

**Реализовано и покрыто тестами:**

- Все доменные правила, идемпотентная обработка событий, адаптеры
  Qdrant/BGE-M3/catalog, консюмер, batch use cases reindex/reconcile, CLI
  (`provision`/`reindex`/`reconcile`/`replay-dlq`) — **юнит-тесты + CDC-
  контракт** (golden-примеры + JSON Schema).
- **Integration-тесты (`testcontainers`)**: реальный Qdrant (round-trip,
  `set_payload` сохраняет векторы, hybrid Query API, reindex/reconcile) и
  реальный RabbitMQ (доставка, retry/DLQ-топология, replay-dlq) — `uv run
  pytest -m integration` (нужен Docker).
- **Наблюдаемость (§10)**: `/health` + `/metrics` (Prometheus) через
  `AsgiFastStream`; distributed tracing (OpenTelemetry, opt-in через
  `INDEXING_OTLP_ENDPOINT`) с продолжением трейса из заголовков события.
- **E2E**: проверено в docker-compose (публикация события → точка в Qdrant
  с корректным payload → инкремент метрики).

**Не реализовано (следующие шаги):** `/ready` с отдельной проверкой Qdrant
(сейчас `/health` пингует брокер, а готовность Qdrant гарантируется
провижинингом на старте).
