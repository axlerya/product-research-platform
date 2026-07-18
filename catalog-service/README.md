# catalog-service

Микросервис-**система-источник истины** товарного каталога для платформы
исследования товаров. Хранит товары, категории, бренды, поставщиков, цены,
себестоимость, остатки и метрики в PostgreSQL; отдаёт REST API (FastAPI);
считает маржинальность; надёжно публикует изменения в RabbitMQ по паттерну
**Transactional Outbox**. Начальные данные — идемпотентный seed из
`products_catalog_ru.csv`.

Спроектирован строго по **Clean Architecture**:
`presentation → infrastructure → application → domain` (зависимости внутрь;
домен без фреймворков). Правило зависимостей — исполняемый инвариант
(`import-linter`).

## Требования

- **Docker** + Docker Compose (рекомендуемый способ запуска), либо
- локально: **Python 3.12** и [`uv`](https://docs.astral.sh/uv/).

## Быстрый запуск (Docker Compose)

Все команды — из каталога `catalog-service/`.

```bash
# 1. Поднять postgres + rabbitmq + api + relay (миграции накатятся сами)
docker compose -f docker/docker-compose.yml up -d --build

# 2. Наполнить каталог из CSV (105 товаров) — разовый прогон
docker compose -f docker/docker-compose.yml --profile seed run --rm seed

# Остановить и удалить данные
docker compose -f docker/docker-compose.yml down -v
```

- API: http://localhost:8000, Swagger UI: http://localhost:8000/docs
- RabbitMQ Management: http://localhost:15672 (guest/guest)

## Тестирование API (curl)

```bash
# Health
curl http://localhost:8000/health

# Создать товар (201; заголовки Location и ETag)
curl -i -X POST http://localhost:8000/api/v1/products \
  -H 'Content-Type: application/json' \
  -d '{"sku":"TEST-001","name":"Наушники","category":"Электроника",
       "brand":"AudioMax","supplier":"TechSupply Co",
       "price":"129.99","cost":"65.00","stock":245}'

# Товар по артикулу
curl http://localhost:8000/api/v1/products/by-sku/PROD-001

# Поиск: электроника с маржой ниже 40% в наличии
curl 'http://localhost:8000/api/v1/products?category=Электроника&margin_max=40&in_stock=true'

# Маржинальность по категориям (avg/min/max)
curl http://localhost:8000/api/v1/analytics/margin

# Обновить цену (оптимистичная блокировка через If-Match = ETag)
curl -i -X PATCH http://localhost:8000/api/v1/products/by-sku/PROD-001   # узнать ETag
curl -X PATCH http://localhost:8000/api/v1/products/<id>/commercial \
  -H 'If-Match: "1"' -H 'Content-Type: application/json' \
  -d '{"price":"119.99"}'
```

Каждое изменение попадает в таблицу `outbox` и публикуется relay в
RabbitMQ (exchange `catalog.events`, routing key = тип события).

## Основные эндпоинты

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/v1/products` | создать товар |
| GET | `/api/v1/products` | поиск/фильтры/пагинация |
| GET | `/api/v1/products/{id}` · `/by-sku/{sku}` | товар |
| GET | `/api/v1/products/{id}/margin` | маржа товара |
| PATCH | `/api/v1/products/{id}` · `/commercial` · `/stock` · `/metrics` | правки (If-Match) |
| DELETE | `/api/v1/products/{id}` | soft-delete |
| GET | `/api/v1/analytics/margin` | маржа по категориям |
| GET | `/api/v1/categories` · `/brands` · `/suppliers` | справочники |
| GET | `/health` · `/ready` | liveness/readiness |

## Локальная разработка

```bash
uv sync                                   # установить зависимости
uv run alembic upgrade head               # миграции (нужен запущенный Postgres)
uv run uvicorn catalog_service.main:app   # API
uv run faststream run catalog_service.presentation.messaging.relay_app:app  # relay
uv run python -m catalog_service seed --file ../products_catalog_ru.csv   # seed
```

### Тесты и проверки

```bash
uv run pytest -m "not integration"        # быстрые unit-тесты (без Docker)
uv run pytest                             # весь набор (integration поднимает Postgres в testcontainers — нужен Docker)
uv run ruff check . && uv run ruff format --check .
uv run lint-imports                        # правило зависимостей Clean Architecture
```

Покрытие — 100% (unit + integration на реальном Postgres + TestClient).

## Структура

```
catalog_service/
  domain/          # агрегат Product, VO, события, исключения (чистый stdlib)
  application/     # use cases, порты (Protocol), DTO, маппинг событий
  infrastructure/  # SQLAlchemy (модели/репозитории/UoW), outbox-relay, брокер, CSV, config
  presentation/    # FastAPI (api), FastStream relay-app, Typer CLI
  bootstrap.py     # composition root (проводка портов ↔ адаптеров)
  main.py          # ASGI-приложение
alembic/           # миграции (0001 baseline, 0002 relay)
tests/             # unit / integration
docker/            # Dockerfile, docker-compose.yml, entrypoint.sh
```
