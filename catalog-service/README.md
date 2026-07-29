# catalog-service

Источник истины товарного каталога платформы: товары, справочники (категории,
бренды, поставщики), цены, себестоимость, остатки и метрики продаж. Пишут сюда
через HTTP-API и CLI-seed из CSV, читают — тоже по HTTP. Каждое изменение
каталога уезжает в RabbitMQ, причём событие пишется в ту же транзакцию, что и
сам товар, — расхождения «сохранили, но не опубликовали» тут не бывает.

Стек: Python 3.12, FastAPI, SQLAlchemy 2.0 (async) + PostgreSQL, FastStream
(RabbitMQ), Typer, Alembic. Clean Architecture с проверяемым правилом
зависимостей.

## Место в платформе: HTTP для чтения, шина для изменений

```
   админка / скрипты ──HTTP──┐
   indexing-service ─────────┤
   research-agent-service ───┴──> catalog-api ──> PostgreSQL
                                                  products + outbox
                                                       │ polling
                                                       ▼
                                                 catalog-relay
                                                       │ publish
                                                       ▼
                                RabbitMQ: exchange catalog.events (topic)
                                          routing key catalog.product.*
                                                       │
                                                       ▼
                                                indexing-service
```

`indexing-service` подписан на `catalog.events` привязкой `catalog.product.*` и
строит из событий поисковую read-model в Qdrant; он же добирает по HTTP
`GET /api/v1/products/{id}` и `GET /api/v1/products`. `research-agent-service`
ходит только за чтением: `POST /api/v1/products/by-skus` и
`POST /api/v1/analytics/prices`.

Событий ровно четыре: `catalog.product.created`, `.content_changed`,
`.commercial_data_changed`, `.deleted`. Routing key равен типу события. Очереди
и привязки объявляет потребитель — каталог о них ничего не знает и публикует
только в exchange.

В `payload` лежит самодостаточный конверт: `event_id`, `event_type`,
`event_version` (`"1.0"`), `aggregate_type`, `aggregate_id`, `sku`,
`aggregate_version`, `occurred_at`, `producer`, `data`. Деньги и рейтинг
сериализуются строками, чтобы не потерять точность на JSON-числах.

Один образ обслуживает три роли: `api` (uvicorn), `relay` (faststream) и разовый
`seed` (Typer CLI).

## Запуск в общем стенде платформы

Из корня репозитория:

```bash
cp .env.example .env          # пароли берутся отсюда, иначе DSN соберётся пустым
docker compose up -d --build
docker compose --profile seed run --rm catalog-seed
```

Без GPU — тот же стенд с оверлеем:
`docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build`.

`catalog-relay` намеренно ждёт готовности `indexing-consumer`: пока очередь не
объявлена, брокер возвращает публикации отправителю (см. «Грабли»).

## Изолированный стенд: только каталог и его инфраструктура

Свой compose поднимает Postgres, RabbitMQ, API и relay без остальных сервисов
платформы. Из каталога `catalog-service/`:

```bash
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml --profile seed run --rm seed
```

Потребителя событий тут нет, поэтому relay будет получать возвраты от брокера —
для отладки API и seed это не мешает.

## Локальный запуск через uv

Дефолты `Settings` совпадают с изолированным стендом (`localhost:5432`,
`guest@localhost:5672`), так что достаточно поднять из него инфраструктуру —
`docker compose -f docker/docker-compose.yml up -d postgres rabbitmq` — а
приложение запустить рядом:

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn catalog_service.main:app --reload
uv run faststream run catalog_service.presentation.messaging.relay_app:app
uv run python -m catalog_service seed --file ../products_catalog_ru.csv
```

Файл `.env` рядом с `pyproject.toml` подхватывается автоматически, но не
обязателен: у каждой переменной есть значение по умолчанию.

## Что открыть после старта

| Что | Общий стенд | Изолированный |
|---|---|---|
| API | `http://localhost:8001` | `http://localhost:8000` |
| Swagger UI / OpenAPI | `/docs`, `/openapi.json` | то же |
| Liveness / readiness | `/health`, `/ready` | то же |
| RabbitMQ Management | `http://localhost:15672` | `http://localhost:15672` (guest/guest) |
| PostgreSQL | `localhost:15432` | `localhost:5432` |

## API: команды двигают версию, чтения её показывают

| Метод и путь | Что делает |
|---|---|
| `POST /api/v1/products` | создаёт товар (201, `Location`, `ETag`) |
| `PATCH /api/v1/products/{id}` | контент: `name`, `description`, `category`, `brand` |
| `PATCH /api/v1/products/{id}/commercial` | `price`, `cost`, `supplier` |
| `PATCH /api/v1/products/{id}/stock` | абсолютный остаток |
| `PATCH /api/v1/products/{id}/metrics` | продажи, рейтинг, отзывы |
| `DELETE /api/v1/products/{id}` | мягкое удаление (204) |
| `GET /api/v1/products` | поиск с фасетами и offset-пагинацией |
| `GET /api/v1/products/{id}`, `/by-sku/{sku}` | одна карточка |
| `POST /api/v1/products/by-skus` | пачка по артикулам плюс `missing_skus` |
| `GET /api/v1/products/{id}/margin` | маржа товара |
| `GET /api/v1/categories`, `/brands`, `/suppliers` | справочники с числом активных товаров |
| `GET /api/v1/analytics/margin` | маржа по категориям (avg/min/max) |
| `POST /api/v1/analytics/prices` | статистика цен и маржи по срезу |

Создание возвращает `ETag` с текущей версией и `Location` на созданный ресурс:

```bash
curl -i -X POST http://localhost:8001/api/v1/products \
  -H 'Content-Type: application/json' \
  -d '{"sku":"PROD-900","name":"Тестовый товар","description":"Заведён через API",
       "category":"Электроника","brand":"AudioMax","supplier":"TechSupply Co",
       "price":"199.99","cost":"120.00","stock":10}'
# 201 Created
# Location: /api/v1/products/019878e3-...
# ETag: "1"
# {"id":"019878e3-...","sku":"PROD-900","version":1}
```

Любое изменение требует `If-Match` с версией из последнего `ETag`. Заголовка нет
— 428, версия устарела — 409 с телом `application/problem+json` и кодом
`concurrency_conflict`:

```bash
curl -i -X PATCH http://localhost:8001/api/v1/products/$ID/commercial \
  -H 'Content-Type: application/json' -H 'If-Match: "1"' \
  -d '{"price":"179.99"}'
# 200 OK, ETag: "2"
```

Поиск принимает `q` (подстрока в названии или описании через `ILIKE`, ускорено
trgm-индексом), фасеты `category`/`brand`/`supplier`, диапазоны
`price_min`/`price_max`/`margin_min`/`margin_max`, флаги `in_stock`,
`include_deleted`, сортировку `sort` (`created_at`, `price`, `margin`, `rating`,
`sales`, `name`; префикс `-` — по убыванию) и `limit`/`offset`:

```bash
curl -G http://localhost:8001/api/v1/products \
  --data-urlencode 'q=наушники' -d 'margin_min=40' -d 'sort=-margin' -d 'limit=5'
```

Batch-чтение не считает неизвестный артикул ошибкой — он приезжает в
`missing_skus`:

```bash
curl -X POST http://localhost:8001/api/v1/products/by-skus \
  -H 'Content-Type: application/json' \
  -d '{"skus":["PROD-001","PROD-404"]}'
```

Ценовой анализ считает срез целиком: статистику цен, статистику маржи,
распределение по бэндам и выбросы. Оба поля запроса необязательны, пустой `{}`
даст анализ по всему каталогу:

```bash
curl -X POST http://localhost:8001/api/v1/analytics/prices \
  -H 'Content-Type: application/json' \
  -d '{"selector":{"category":"Электроника"},
       "bands":[{"label":"до 30%","upper_percent":30},
                {"label":"30–50%","lower_percent":30,"upper_percent":50}]}'
```

Удаление тоже требует версию:
`curl -i -X DELETE http://localhost:8001/api/v1/products/$ID -H 'If-Match: "2"'`
вернёт 204.

Ошибки везде отдаются в формате RFC 9457 (`application/problem+json`) с машинным
кодом в поле `code`: `product_not_found`, `duplicate_sku`,
`concurrency_conflict`, `mixed_currency_slice`, `validation_error`.

## Конфигурация

Все переменные читаются с префиксом `CATALOG_` из окружения или `.env` в рабочем
каталоге. Обязательных нет — сервис поднимется на дефолтах, рассчитанных на
локальный compose.

| Переменная | Зачем | По умолчанию |
|---|---|---|
| `CATALOG_DATABASE_URL` | DSN PostgreSQL (драйвер `asyncpg`) | `postgresql+asyncpg://catalog:catalog@localhost:5432/catalog` |
| `CATALOG_RABBITMQ_DSN` | DSN RabbitMQ для relay | `amqp://guest:guest@localhost:5672/` |
| `CATALOG_DEFAULT_CURRENCY` | валюта сервиса; в API не передаётся | `RUB` |
| `CATALOG_SQL_ECHO` | печатать SQL в лог | `false` |
| `CATALOG_OUTBOX_POLL_INTERVAL_S` | пауза между проходами relay | `1.0` |
| `CATALOG_OUTBOX_BATCH_SIZE` | размер батча выборки из outbox | `100` |
| `CATALOG_OUTBOX_MAX_ATTEMPTS` | после скольких неудач строка уходит в карантин | `10` |
| `CATALOG_LOG_LEVEL` | объявлен в настройках, но логирование по нему пока не конфигурируется | `INFO` |

## Как устроен код

```
catalog_service/
  domain/          сущности, value objects, доменные события, доменные ошибки
  application/     use cases, порты (Protocol), DTO, маппинг событий в outbox
  infrastructure/  SQLAlchemy, репозитории, UnitOfWork, RabbitMQ, CSV, настройки
  presentation/    FastAPI (роутеры и Pydantic-схемы), FastStream relay, Typer CLI
  bootstrap.py     composition root: связывает порты с адаптерами
  main.py          ASGI-объект app для uvicorn
```

Зависимости направлены внутрь: `presentation` и `infrastructure` знают про
`application`, `application` — про `domain`, `domain` не знает ни про кого.
Домен и прикладной слой не импортируют ни SQLAlchemy, ни FastAPI, ни Pydantic;
роутеры не импортируют `infrastructure` — реализации им подсовывает composition
root через `dependency_overrides`.

Это не соглашение на словах: четыре контракта `import-linter` в `pyproject.toml`
падают на нарушении, плюс ruff запрещает импорты фреймворков вне разрешённых
пакетов (`TID251`).

## Решения, которые важны в эксплуатации

**Transactional Outbox.** Мутация товара и строка события пишутся одной
транзакцией через общую сессию `UnitOfWork`, поэтому опубликованных событий без
изменения в базе (и наоборот) не существует. Отдельный процесс `catalog-relay`
опрашивает таблицу `outbox` каждые `CATALOG_OUTBOX_POLL_INTERVAL_S`, выбирает
батч через `FOR UPDATE SKIP LOCKED` (можно держать несколько relay без дублей),
публикует и проставляет `published_at`. Гарантия — at-least-once: потребитель
обязан быть идемпотентным, и для этого у сообщения есть `message_id` (он же
`event_id` в конверте) и `aggregate_version` — в заголовках AMQP и в теле.

**Возврат от брокера считается ошибкой.** Брокер создаётся с
`on_return_raises=True`, поэтому публикация в topic-exchange, к которому не
привязана подходящая очередь, не помечается успешной. Строка получает
`attempts + 1`, `last_error` и `next_attempt_at` с экспоненциальным backoff
(потолок 300 секунд), а после `CATALOG_OUTBOX_MAX_ATTEMPTS` уходит в карантин —
`failed_at`, из выборки исключается.

**Оптимистичная блокировка.** У товара есть `version`; репозиторий обновляет
строку условием `WHERE id = ... AND version = expected`, и нулевой `rowcount`
превращается в 409. За одну команду версия растёт не больше чем на единицу, а
мутатор, которому передали текущее же значение, ничего не меняет и события не
порождает.

**Метрики двигают версию, но события не дают.** `PATCH /metrics` меняет продажи,
рейтинг и число отзывов и бампает `version`, однако в шину ничего не уходит —
поисковая read-model об этом изменении не узнает. Так задумано: метрики шумные и
переиндексацию не оправдывают.

**Идемпотентный seed.** CLI гоняет CSV через те же доменные методы, что и API:
для каждой строки — upsert по артикулу, агрегат сам классифицирует diff в
события. Повторный прогон неизменного файла создаёт ноль событий. По умолчанию
`--on-stale skip` защищает ручные правки: строка с `последнее_обновление` не
новее сохранённого пропускается; `--on-stale overwrite` эту защиту снимает.
Отчёт печатается в stdout, при ошибках строк процесс выходит с кодом 1.

**Маржа считается в двух местах и одинаково.** Домен считает
`(price - cost) / price * 100` с округлением half-up до сотых, `None` при
нулевой цене. В таблице `products` та же формула лежит GENERATED-колонкой
`margin_percent` — по ней работают фильтры, сортировка и аналитика, без
пересчёта на чтении.

**Read-модель ходит мимо ORM.** Поиск и аналитика выполняются параметризованным
SQL и собирают DTO-представления напрямую, без гидрации агрегата: значения
фильтров идут только bound-параметрами, а `sort` разрешается по whitelist
колонок. Агрегат восстанавливается лишь на записи.

## Разработка и тесты

```bash
uv sync
uv run ruff check .            # линт, длина строки 80
uv run lint-imports            # правило зависимостей Clean Architecture
uv run pytest -m "not integration"   # быстрый прогон, без Docker
uv run pytest --cov            # весь набор с покрытием
```

Integration-тесты поднимают настоящий Postgres через `testcontainers` (образ
`postgres:16-alpine`), накатывают схему боевыми миграциями Alembic, а не
`create_all`, и чистят таблицы перед каждым тестом — значит, нужен работающий
Docker. Порог покрытия — 90% (`fail_under`), считается по ветвям. Порядок тестов
перемешивается `pytest-randomly`, маркеры проверяются строго (`integration`,
`contract`, `slow`).

## Миграции накатываются на старте контейнера

`docker/entrypoint.sh` дожидается Postgres и выполняет `alembic upgrade head`
перед любой командой, поэтому в compose руками ничего накатывать не нужно.
Локально — `uv run alembic upgrade head`; URL базы `alembic/env.py` берёт из тех
же `Settings`.

Новую ревизию заводите руками: `uv run alembic revision -m "что меняем"`.
`--autogenerate` здесь опасен: GENERATED-колонка `margin_percent`, частичные и
trgm-индексы, уникальность SKU описаны только в миграциях и отсутствуют в
ORM-моделях, так что автогенератор предложит их снести.

## Грабли

- **Relay стартует после потребителя.** Если поднять relay раньше, чем
  `indexing-consumer` объявит очередь, публикации будут возвращаться брокером,
  попытки — расти, а после десятой строка уйдёт в карантин и сама уже не поедет.
  В общем стенде порядок зафиксирован через `depends_on`; в изолированном
  compose потребителя нет вовсе.
- **`products_catalog_ru.csv` не лежит в репозитории** — он в `.gitignore`.
  Положите файл в корень до запуска профиля `seed`, иначе Docker смонтирует
  пустую директорию вместо файла.
- **Корневой `.env` обязателен для общего стенда.** Пароли Postgres и RabbitMQ
  подставляются из него; без файла compose соберёт DSN с пустым паролем, и
  контейнеры не подключатся.
- **`If-Match` нужен всем `PATCH` и `DELETE`.** Без заголовка ответ 428, а не
  200; значение — версия из `ETag` предыдущего ответа, кавычки обязательны
  (форма `W/"2"` тоже принимается).
- **Артикул нормализуется не везде одинаково.** Чтения (`/by-sku/{sku}`,
  `by-skus`, селектор аналитики) и seed делают `strip().upper()`, так что
  `prod-001` найдёт `PROD-001`. А вот `POST /products` валидирует поле схемой по
  паттерну `^[A-Z0-9][A-Z0-9-]{1,62}[A-Z0-9]$` до того, как домен успеет
  нормализовать, и на строчных буквах вернёт 422.
- **Уникальность SKU распространяется на удалённые.** Мягко удалённый товар
  продолжает держать свой артикул: создать новый с тем же SKU не выйдет.
