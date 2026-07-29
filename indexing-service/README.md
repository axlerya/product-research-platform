# indexing-service

Слушает события товарного каталога и держит коллекцию Qdrant в состоянии,
пригодном для гибридного поиска. Векторы сам не считает: заказывает их у
embedding-service командой в `embedding.jobs` и применяет результат из
`embedding.events`. Коллекцию читает research-agent-service, поэтому свежесть
read-model — ответственность этого сервиса, а не поискового клиента. Python
3.12, Clean Architecture, FastStream поверх RabbitMQ, Postgres под задания и
transactional outbox.

## Конвейер разведён на две фазы и два exchange

Событие каталога и результат эмбеддинга приходят по разным маршрутам. Ни в одной
точке сервис не ждёт ответа синхронно: RPC к embedding-service нет, обращение к
нему — это команда в брокер и отдельное событие в ответ.

```
catalog-service
   │  exchange catalog.events (topic), routing key catalog.product.*
   ▼
indexing-consumer ─────────────▶ Qdrant: карточка товара, векторов ещё нет
   │
   └─ одной транзакцией Postgres: indexing_jobs + embedding_requests + outbox
                                        │
                                        ▼
                                 indexing-relay (polling outbox)
                                        │  exchange embedding.jobs (topic)
                                        │  embedding.documents.requested.v1
                                        ▼
                               embedding-service (BGE-M3)
                                        │  exchange embedding.events (topic)
                                        │  embedding.documents.generated.v1
                                        ▼
                             indexing-result-consumer
                                        │
                                        ▼
                     Qdrant: dense + sparse дописываются на ту же точку
```

Фаза A (`ProcessCatalogEvent` → `RequestEmbedding`) кладёт в Qdrant всю карточку
товара **без** `content_hash` и `model_version`. Эти два поля — водяные знаки
«текст проиндексирован», и ставит их только тот, кто реально посчитал векторы.
Поставь их раньше — дедуп в `classify` навсегда закроет товару путь к пересчёту.

Фаза B (`ApplyEmbeddingResult` → `QdrantEmbeddingSink`) дописывает векторы
**мерджем**: `update_vectors` плюс `set_payload`, а не `upsert`. Полный `upsert`
снёс бы цену, остаток и маржу, которые тем временем успел записать горячий путь.

## Коммерческие изменения не пересчитывают эмбеддинги

Текст документа собирает `document_composer.compose` из четырёх полей: `name`,
`brand`, `category`, `description`. Цена, себестоимость, остаток, поставщик и
метрики в текст не входят — значит их изменение не может изменить вектор, и
звать embedding-service незачем.

Решение принимает `domain/services/change_classifier.py`:

| Событие | Состояние точки | Действие | Идёт в embedding-service |
|---|---|---|---|
| `catalog.product.created` | любое | `FULL_INDEX` | да |
| `catalog.product.content_changed` | текст новый | `REEMBED` | да |
| `catalog.product.content_changed` | `content_hash` и модель те же | `PAYLOAD_ONLY` | нет |
| `catalog.product.commercial_data_changed` | точка есть | `PAYLOAD_ONLY` | нет |
| `catalog.product.deleted` | точка есть | `TOMBSTONE` | нет |
| `content_changed` / `commercial_data_changed` | точки нет | `REPAIR` | да |
| любое | `event_version < watermark` | `SKIP` | нет |

`REPAIR` — это дыра в потоке событий: пришло частичное изменение, а товара в
индексе нет. Тогда сервис берёт снимок из catalog-service по REST
(`GET /api/v1/products/{id}`) и индексирует его целиком. Ради этого случая и
живёт `infrastructure/catalog/http_client.py`; он же обходит каталог постранично
для `reindex` и `reconcile`.

Guard по версии строгий: отбрасывается только то, что **строго** перекрыто более
новой версией. События одной версии — сиблинги одной команды каталога — доходят
до обработки.

## Три процесса, а не один

| Роль | Команда | Порт в корневом compose | Что делает |
|---|---|---|---|
| `indexing-consumer` | `uvicorn indexing_service.presentation.messaging.consumer_app:app` (CMD образа) | 8020 → 8000 | Читает `catalog.events`, пишет карточку в Qdrant, ставит job и команду в outbox |
| `indexing-relay` | `uvicorn indexing_service.presentation.messaging.relay_app:app` | 8021 → 8000 | Опрашивает outbox, публикует команды в `embedding.jobs`, переснимает метрики отставания |
| `indexing-result-consumer` | `uvicorn indexing_service.presentation.messaging.result_consumer_app:app` | 8022 → 8000 | Читает `embedding.events`, дописывает векторы в Qdrant, закрывает job |

Каждая роль отдаёт `/health` (пинг брокера) и `/metrics` (Prometheus, свой
`CollectorRegistry` на процесс).

Миграции и провижининг привязаны к консюмеру каталога. `docker/entrypoint.sh`
вызывает `alembic upgrade head` только при `RUN_MIGRATIONS=1`, а этот флаг стоит
**только** у `indexing-consumer`; иначе три процесса полезли бы в alembic
одновременно. Он же единственный вызывает `CollectionProvisioner.ensure()` и
`point_alias()` при старте — relay и result-consumer коллекцию не создают.

Отсюда порядок старта: сначала `indexing-consumer` (схема БД + коллекция +
очередь `indexing.catalog.products`), потом остальные. Relay в корневом compose
дополнительно ждёт `embedding` по healthcheck: очередь под команды объявляет
embedding-service, а publish в topic-exchange без подходящей очереди брокер
возвращает отправителю. Возврат теперь замечается (`on_return_raises=True`) и
уходит в backoff, но на холодном старте это стоило бы минут ожидания.

## Быстрый запуск

Весь стенд платформы поднимается из корня репозитория:

```bash
cp .env.example .env          # иначе пароли подставятся пустыми строками
docker compose up -d --build
docker compose --profile seed run --rm catalog-seed
```

Отдельный стенд только под этот сервис (Qdrant + Postgres + RabbitMQ + три роли)
лежит в `docker/docker-compose.yml`. Профиль `fake-embedding` поднимает заглушку
из `indexing_service/tools/fake_embedding_service.py`: она отвечает на команды
детерминированными векторами, и конвейер прогоняется целиком без модели и GPU.
Размерность там намеренно `8`:

```bash
docker compose -f docker/docker-compose.yml --profile fake-embedding up -d --build
```

Локально, без Docker для самого сервиса:

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run python -m indexing_service provision
uv run uvicorn indexing_service.presentation.messaging.consumer_app:app --port 8000
uv run uvicorn indexing_service.presentation.messaging.relay_app:app --port 8001
uv run uvicorn indexing_service.presentation.messaging.result_consumer_app:app --port 8002
```

### Проверить, что коллекция создана и наполняется

Физическая коллекция называется `products_v1`, публичный алиас — `products`.

```bash
# алиас есть и указывает на products_v1
curl -s http://localhost:6333/aliases

# схема: dense/sparse и размерность
curl -s http://localhost:6333/collections/products

# сколько карточек всего
curl -s -X POST http://localhost:6333/collections/products/points/count \
  -H 'Content-Type: application/json' -d '{"exact": true}'

# сколько из них уже получили векторы: model_version ставит только фаза B
curl -s -X POST http://localhost:6333/collections/products/points/count \
  -H 'Content-Type: application/json' \
  -d '{"exact": true, "filter": {"must_not": [{"is_empty": {"key": "model_version"}}]}}'

# посмотреть на одну точку целиком
curl -s -X POST http://localhost:6333/collections/products/points/scroll \
  -H 'Content-Type: application/json' \
  -d '{"limit": 1, "with_payload": true, "with_vector": true}'
```

Если первое число растёт, а второе стоит — фаза A работает, фаза B нет: смотрите
relay, `embedding.jobs` и очередь `indexing.embeddings.generated`.

## Что лежит в Qdrant

Точка товара — это UUID товара строкой. Чанки (появляются только после дробления
слишком длинного текста) получают производные UUID; нулевой под-чанк намеренно
остаётся на точке родителя, чтобы коммерческий payload не осиротел.

**Именованные векторы** — кросс-сервисный контракт, их имена передаются в
`using=` при гибридном поиске:

- `dense` — `VectorParams(size=INDEXING_EMBEDDING_DIM, distance=COSINE)`;
- `sparse` — `SparseVectorParams()` **без** `modifier=IDF`: веса BGE-M3 уже
  финальные.

**Payload** (`application/payload.py`): `product_id`, `sku`, `name`,
`description`, `category`, `brand`, `supplier`, `price`, `cost`, `currency`,
`stock`, `in_stock`, `margin_percent`, `sales_per_month`, `rating`,
`review_count`, `source_updated_at`, `aggregate_version`, `indexed_at`,
`is_deleted`. Плюс поля, которые ставит только фаза B: `content_hash`,
`model_version`, `content_version`, `chunk_ix`, `token_count`, `reindex_epoch`.
Tombstone добавляет `deleted_at`.

Деньги лежат `float`, а не `Decimal`: по ним фильтрует `Range`. Точные значения
остаются в catalog-service.

**Payload-индексы** заводятся при создании коллекции
(`collection_spec.PAYLOAD_INDEXES`): keyword — `sku`, `category`, `brand`,
`supplier`, `model_version`, `product_id`, `reindex_epoch`; float — `price`,
`cost`, `rating`, `margin_percent`; integer — `stock`, `sales_per_month`,
`review_count`, `aggregate_version`, `content_version`, `chunk_ix`; bool —
`in_stock`, `is_deleted`; datetime — `indexed_at`.

## Контракты сообщений

Все схемы и golden-примеры лежат в `contracts/` и проверяются контрактными
тестами.

**Принимает** из `catalog.events` (topic) по `catalog.product.*` — конверт с
обязательными `event_id`, `event_type`, `aggregate_id`, `sku`,
`aggregate_version`, `occurred_at`, `data`. Четыре типа:
`catalog.product.created`, `.content_changed`, `.commercial_data_changed`,
`.deleted`. Reader толерантный (`extra="ignore"`), деньги и рейтинг приходят
строками. У `created` метрики вложены в `data.metrics`, в отличие от REST, где
они на верхнем уровне.

**Публикует** в `embedding.jobs` (topic), routing key =
`embedding.documents.requested.v1`:

```json
{
  "event_id": "…", "event_type": "embedding.documents.requested.v1",
  "event_version": "1.0", "aggregate_type": "embedding_job",
  "aggregate_id": "<request_id>", "occurred_at": "…",
  "producer": "read-model-builder",
  "data": {
    "request_id": "…", "model": "BAAI/bge-m3",
    "return_dense": true, "return_sparse": true,
    "items": [{"text_id": "<point_id>", "text": "Товар: …\nБренд: …"}]
  }
}
```

`model` попадает в команду только если задан `INDEXING_EXPECTED_MODEL`; иначе
embedding-service берёт свою модель по умолчанию. Длина `items` ограничена
`INDEXING_MAX_TEXTS` — длиннее команда режется на несколько.

**Читает** из `embedding.events` (topic) по `embedding.documents.generated.v1`.
Из `data` используются `request_id`, `model_version`, `dim` и массив `results` с
полями `text_id`, `status` (`ok` / `error`), `dense`, `sparse.indices`,
`sparse.values`, `token_count`, `error.code`. Известные коды ошибок:
`EMPTY_TEXT`, `TEXT_TOO_LONG`, `TOKENS_EXCEEDED`, `INFERENCE_FAILED`.

## Конфигурация

Все переменные читаются с префиксом `INDEXING_` (pydantic-settings, файл
`.env`). Обязательных нет — у каждой есть дефолт под локальный стек, но в
compose переопределяются адреса и размерность.

| Переменная | Назначение | Дефолт |
|---|---|---|
| `INDEXING_RABBITMQ_DSN` | Брокер | `amqp://guest:guest@localhost:5672/` |
| `INDEXING_DATABASE_URL` | Postgres под jobs и outbox | `postgresql+asyncpg://indexing:indexing@localhost:5432/indexing` |
| `INDEXING_SQL_ECHO` | Логировать SQL | `false` |
| `INDEXING_QDRANT_URL` | Адрес Qdrant | `http://localhost:6333` |
| `INDEXING_QDRANT_API_KEY` | Ключ Qdrant | пусто |
| `INDEXING_COLLECTION_ALIAS` | Алиас чтения; коллекция — `<alias>_v1` | `products` |
| `INDEXING_CATALOG_BASE_URL` | catalog-service для repair/reindex/reconcile | `http://localhost:8000` |
| `INDEXING_EMBEDDING_DIM` | Размерность dense; ей создаётся коллекция и по ней валидируется результат | `1024` |
| `INDEXING_EXPECTED_MODEL` | Закреплённая модель; пусто — дрейф ловит `reconcile` | пусто |
| `INDEXING_MAX_TEXTS` | Предел `items` в одной команде | `32` |
| `INDEXING_PREFETCH_COUNT` | QoS консюмеров | `32` |
| `INDEXING_MAX_ATTEMPTS` | Проходов по retry-лестнице до parking | `5` |
| `INDEXING_RETRY_TTL_MS` | Выдержка в retry-очереди | `30000` |
| `INDEXING_OUTBOX_POLL_INTERVAL_S` | Пауза между проходами relay | `1.0` |
| `INDEXING_OUTBOX_MAX_ATTEMPTS` | Попыток публикации строки outbox до карантина | `10` |
| `INDEXING_OUTBOX_BATCH_SIZE` | Размер батча выборки outbox | `100` |
| `INDEXING_MAX_ITEM_ATTEMPTS` | Попыток эмбеддинга одного чанка | `5` |
| `INDEXING_ITEM_RETRY_BACKOFF_S` | База экспоненциального backoff чанка | `5.0` |
| `INDEXING_ITEM_RETRY_BACKOFF_CAP_S` | Потолок backoff | `300.0` |
| `INDEXING_JOB_TIMEOUT_S` | Через сколько команда считается потерянной (`reconcile`) | `900.0` |
| `INDEXING_MAX_REQUEST_ATTEMPTS` | Сколько раз переспрашивать зависшую команду | `5` |
| `INDEXING_OTLP_ENDPOINT` | OTLP/HTTP endpoint трейсинга; пусто — выключен | пусто |
| `INDEXING_SERVICE_NAME` | Имя сервиса в трейсах | `indexing-service` |

`RUN_MIGRATIONS` читает не приложение, а `docker/entrypoint.sh`; префикса у неё
нет. `INDEXING_DEFAULT_CURRENCY`, `INDEXING_SOURCE_MODE` и `INDEXING_LOG_LEVEL`
объявлены в `Settings`, но ни один кодовый путь их пока не читает.

## Как устроен код

```
indexing_service/
  domain/          сущности, VO, доменные сервисы: классификация изменений,
                   composer текста, чанкинг, водяной знак, статусы job
  application/     use cases, порты, DTO, сборка команды и строки outbox
  infrastructure/  Qdrant, Postgres + Alembic, RabbitMQ, HTTP-клиент catalog,
                   метрики, трейсинг, outbox-relay
  presentation/    три FastStream-приложения, схемы и разбор конвертов,
                   политика ack/retry/DLQ, Typer CLI
  bootstrap.py     composition root: единственное место, знающее все слои
```

Зависимости направлены внутрь: `presentation`/`infrastructure` → `application` →
`domain`. Это не соглашение на словах, а исполняемый инвариант —
`pyproject.toml` описывает контракты import-linter, запрещающие `domain` и
`application` знать про `qdrant_client`, `faststream`, `httpx`, `fastapi`,
`pydantic`, `sqlalchemy`, `asyncpg`, `alembic`. Ruff дублирует запрет на уровне
импортов (`TID251`) с исключениями для `infrastructure`, `presentation`,
`bootstrap.py` и `tools`.

## Надёжность

**Одна транзакция вместо двух записей.** `RequestEmbedding` пишет
`indexing_jobs`, `embedding_requests` и `outbox` через общую `AsyncSession` и
один `commit()`. Поэтому «job без команды» и «команда без job» невозможны.
Публикует отдельный процесс, читая outbox с `FOR UPDATE SKIP LOCKED`.

**Идемпотентность на трёх уровнях.** Задание уникально по
`(product_id, content_version, COALESCE(target_collection, ''))` — редоставка
события каталога не плодит job. `request_id` детерминирован:
`uuid5(NS, "{job_id}|{attempt}|{sha256(items)}")`, поэтому повторная публикация
даёт тот же id. Повторный результат отсекается по `request.status == done` и
терминальному статусу job.

**Водяные знаки против гонок.** `aggregate_version` в payload — знак «что уже
применено»: событие старее знака отбрасывается. `content_version` — знак версии
текста: `QdrantEmbeddingSink` не пишет результат, если в точке уже лежит версия
не меньше пришедшей, так что опоздавший ответ embedding-service не затрёт свежий
текст. Внутри процесса события одного товара сериализует `AggregateLock`, между
репликами — `x-single-active-consumer` на обеих основных очередях.

**Retry-лестница и DLQ.** У каждого консюмера своя приватная лестница
`main → retry(TTL) → requeue → main`, чтобы ретраи не задевали других
потребителей общих exchange. Постоянная ошибка (битый контракт, неизвестный код,
доменный инвариант) паркуется сразу; временная (Qdrant, Postgres, catalog)
отправляется в retry, а после `INDEXING_MAX_ATTEMPTS` смертей по заголовку
`x-death` — в parking.

| | Основная очередь | Retry | Parking |
|---|---|---|---|
| События каталога | `indexing.catalog.products` | `indexing.catalog.products.retry` | `indexing.catalog.products.dlq` |
| Результаты эмбеддинга | `indexing.embeddings.generated` | `indexing.embeddings.generated.retry` | `indexing.embeddings.generated.dlq` |

**Ошибки уровня элемента.** `INFERENCE_FAILED` — повтор упавших чанков с
экспоненциальным backoff. `TOKENS_EXCEEDED` и `TEXT_TOO_LONG` — текст режется
примерно пополам и заменяется под-чанками (точного лимита модели событие не
сообщает). `EMPTY_TEXT` — перманентный отказ без повторов.

**Сверка двух видов.** `ReconcileCatalog` сравнивает каталог с Qdrant: чинит
дрейф метрик через `set_payload` без пересчёта векторов, ставит задание там, где
текст или модель разошлись, и закрывает tombstone'ом точки, которых в каталоге
больше нет. `ReconcileJobs` смотрит с другой стороны — находит команды старше
`INDEXING_JOB_TIMEOUT_S` без ответа и переспрашивает с `attempt+1`.

**Дедуп по тексту.** Если `content_changed` пришёл с тем же `content_hash` (и
той же моделью, когда она закреплена), классификация отдаёт `PAYLOAD_ONLY`:
текст обновляется, эмбеддинг не заказывается.

## Разработка и тесты

```bash
uv sync                                    # включая dev-группу
uv run ruff check .
uv run lint-imports                        # контракты слоёв из pyproject.toml
uv run pytest -m "not integration"         # unit + contract, без Docker
uv run pytest -m integration               # testcontainers: Qdrant, RabbitMQ, Postgres
uv run pytest --cov --cov-report=term-missing
```

Маркеры объявлены в `pyproject.toml` и строгие (`--strict-markers`):
`integration`, `contract`, `slow`. Порядок тестов рандомизирован
(`pytest-randomly`), `asyncio_mode = "auto"`. Порог покрытия — 90 %, из подсчёта
исключены composition root и runtime-обвязка.

Интеграционные тесты поднимают настоящие Qdrant `v1.13.5`, RabbitMQ `3.13` и
Postgres 16 через testcontainers — нужен доступный Docker. Схема в тестовой БД
накатывается теми же миграциями Alembic, что и в проде.

Миграции:

```bash
uv run alembic upgrade head
uv run alembic revision -m "описание"      # автогенерация не используется:
                                           # DDL пишется руками (см. versions/)
```

URL берётся из `Settings`, если не задан в `alembic.ini`. Таблицы:
`indexing_jobs`, `embedding_requests`, `outbox`.

CLI (`python -m indexing_service`, Typer):

| Команда | Что делает |
|---|---|
| `provision` | Создаёт коллекцию и направляет на неё алиас |
| `reconcile` | Прогоняет обе сверки: каталог ↔ Qdrant и зависшие команды |
| `reindex --target products_v2` | Провижинит новую коллекцию и ставит задания на весь каталог |
| `reindex-swap --target products_v2 [--min-ready 1.0]` | Переключает алиас, если эпоха действительно готова |
| `replay-dlq` | Возвращает запаркованные события каталога в `catalog.events` |

`reindex` и `reindex-swap` разделены намеренно: задания ставятся за минуты, а
векторы считаются часами. Перед свапом готовность проверяется дважды — по
статусам job в Postgres и по фактическому числу точек с меткой эпохи в самой
коллекции. Задания могут быть закрыты, а векторы уйти не туда — тогда алиас
отдал бы поиску пустышку.

## Типичные грабли

**`INDEXING_EMBEDDING_DIM` разошлась с `EMBEDDING_DIM` у embedding-service.**
Коллекция создаётся под одну размерность, а `ApplyEmbeddingResult` сверяет
`data.dim` результата со своей и роняет событие как невалидное — оно уходит в
parking, векторов в Qdrant не появляется. Значения зафиксированы рядом в
корневом `docker-compose.yml`, менять их нужно парой.

**Relay стартовал раньше времени.** Если `embedding-service` ещё не объявил свою
очередь, брокер вернёт команду отправителю. `on_return_raises=True` не даёт
пометить такую строку опубликованной, но выйти из backoff она сможет далеко не
сразу. Соблюдайте порядок: `indexing-consumer` → `embedding` → `indexing-relay`.

**Размерность в локальном стенде — не 1024.** `docker/docker-compose.yml` ставит
`INDEXING_EMBEDDING_DIM: "8"` под заглушку. Том `qdrant_data` переживает
пересоздание контейнеров, поэтому коллекция, созданная под 8, останется такой и
после переключения на боевую модель. Тогда её нужно удалить или
переиндексировать в новую.

**Ручной ре-индекс — это не одна команда.** `reindex` только ставит задания;
алиас переключает `reindex-swap`, и он вернёт код 1, пока эпоха не готова. Между
ними должны работать relay и result-consumer, иначе счётчик готовности не
сдвинется. Горячий путь при этом продолжает писать в живой алиас — эпоха его не
останавливает.

**`INDEXING_EXPECTED_MODEL` задан не тем значением.** Сверка идёт точным
равенством с `model_version` из события-результата, а embedding-service
присылает не голое имя модели, а ключ вида
`BAAI/bge-m3@unknown|pool=cls|norm=1|dim=1024`. Не угадали строку — `reconcile`
будет вечно считать модель устаревшей, а `reindex-swap` не насчитает ни одной
готовой точки эпохи и не переключит алиас. Пустое значение отключает эту сверку
и безопаснее.
