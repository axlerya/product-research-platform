# product-research-platform

ИИ-ассистент для исследования товаров: отвечает на вопросы о каталоге, ищет
рыночную информацию в интернете и детерминированно считает маржинальность.
Каталог живой — цены, остатки и описания меняются постоянно, поэтому поисковый
индекс догоняет изменения сам, без ручного ре-индекса.

Платформа собрана из четырёх Python-микросервисов. Каждый живёт в своём
каталоге, имеет свой `pyproject.toml`, свою базу и свой README.

## Что делает каждый сервис

| Сервис                                              | Роль                                                                            | Хранилище          |
| --------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------ |
| [catalog-service](./catalog-service/README.md)             | Источник истины каталога. REST API, расчёт маржи, публикация изменений в шину    | PostgreSQL         |
| [indexing-service](./indexing-service/README.md)           | Собирает поисковую read-model из событий каталога                               | Qdrant + PostgreSQL |
| [embedding-service](./embedding-service/README.md)         | Эмбеддинги BGE-M3 (dense + sparse) и реранкинг cross-encoder                     | —                  |
| [research-agent-service](./research-agent-service/README.md) | LLM-агент: маршрутизирует запрос по инструментам и собирает ответ с цитатами     | PostgreSQL + Redis |

Пятый каталог, `e2e/`, — не сервис, а стенд: детерминированные заглушки внешних
провайдеров и сквозные тесты поднятой платформы.

## Как запрос проходит через платформу

Каталог и индекс связаны только событиями — синхронных вызовов между ними нет:

```
      изменение товара
             │
    catalog-service ──outbox──▶ catalog.events
                                     │
                            indexing-service ──▶ Qdrant (карточка без векторов)
                                     │
                                     └──outbox──▶ embedding.jobs
                                                       │
                                              embedding-service
                                                       │
                                     embedding.events ─┘
                                             │
                            indexing-service ──▶ Qdrant (dense + sparse)
```

Запрос пользователя идёт по синхронному пути:

```
   POST /query ──▶ research-agent-service
                          ├── gRPC EmbedQuery  ──▶ embedding-service
                          ├── гибридный поиск  ──▶ Qdrant
                          ├── gRPC Rerank      ──▶ embedding-service
                          ├── REST             ──▶ catalog-service
                          └── web-поиск        ──▶ внешний провайдер
```

Изменение цены или остатка обновляет payload в Qdrant напрямую и **не запускает
пересчёт эмбеддингов** — векторы зависят только от текста.

## Запуск стенда

Нужен Docker с Compose. Все команды — из корня репозитория.

Сначала секреты. Без `.env` Compose подставит пустые строки, и стенд не
поднимется: postgres откажется инициализироваться без пароля суперпользователя,
а init-скрипт баз явно проверяет, что переменные заданы.

```bash
cp .env.example .env
```

Значения в `.env.example` — заглушки для локального стенда. Хранилищем секретов
`.env` не является: значения видны в `docker compose config` и `docker inspect`.

Затем поднимите стенд:

```bash
docker compose up -d --build
```

Первый запуск скачивает две модели HuggingFace (около 4.6 ГБ) — контейнер
`embedding` прогревается минутами, и на его готовности завязан старт остальных.
Модели кладутся в том `hf_cache`, повторные запуски прогреваются быстро.

Наполните каталог 105 товарами из `products_catalog_ru.csv` — разовый прогон,
повторный запуск ничего не дублирует:

```bash
docker compose --profile seed run --rm catalog-seed
```

Файл с данными лежит в корне репозитория, но под gitignore, так что в свежем
клоне его нужно положить туда самостоятельно — Compose монтирует его в контейнер
по этому пути.

Остановить стенд и стереть данные:

```bash
docker compose down -v
```

### Без GPU

Базовый файл резервирует NVIDIA GPU. Оверлей переключает обе модели на CPU и
поднимает дедлайны gRPC-вызовов, потому что на CPU реранкинг 60 кандидатов
подходит вплотную к границе:

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build
```

Считает те же модели, только в разы медленнее.

## Куда стучаться

| Адрес                    | Что это                                            |
| ------------------------ | -------------------------------------------------- |
| `http://localhost:8080`  | API агента, Swagger — на `/docs`                    |
| `http://localhost:8081`  | Тот же агент с намеренно недоступным реранкером     |
| `http://localhost:8001`  | API каталога                                        |
| `http://localhost:8010`  | Ops-эндпоинты embedding-service (`/health`, `/ready`) |
| `http://localhost:8020`  | indexing-consumer                                   |
| `http://localhost:8021`  | indexing-relay                                      |
| `http://localhost:8022`  | indexing-result-consumer                            |
| `http://localhost:8090`  | Тестовые провайдеры LLM и web-поиска                |
| `http://localhost:6333`  | Qdrant                                              |
| `http://localhost:15672` | RabbitMQ Management                                 |
| `localhost:15432`        | PostgreSQL                                          |
| `localhost:16379`        | Redis                                               |
| `localhost:50051`        | gRPC embedding-service                              |

## Первый запрос агенту

```bash
curl -X POST http://localhost:8080/query \
  -H 'Content-Type: application/json' \
  -d '{"text": "покажи беспроводные наушники и посчитай маржинальность"}'
```

В ответе:

- `answer` — текст, собранный моделью;
- `used_tools` — какие инструменты сработали: `product_catalog_rag`,
  `price_analysis`, `web_search`;
- `citations` — источник каждого факта: `source_type` (`product`,
  `price_analysis`, `web`), `ref` и `score`. Ссылка ценового анализа — это
  идентификатор среза, по которому результат воспроизводится в каталоге, так что
  число в ответе проверяемо и моделью не выдумано;
- `degradations` — зависимости, которые отвалились, с причиной;
- `confidence` — уверенность, понижается при деградации;
- `agent_run_id` — идентификатор прогона.

Повтор с тем же `idempotency_key` реплеит прежний прогон, а не запускает новый:

```bash
curl -X POST http://localhost:8080/query \
  -H 'Content-Type: application/json' \
  -d '{"text": "покажи беспроводные наушники", "idempotency_key": "demo-1"}'
```

### Проверить деградацию

У `agent-api-degraded` адрес реранкера ведёт в закрытый порт — gRPC отвечает
`UNAVAILABLE`. Ответ всё равно приходит, но с пометкой:

```bash
curl -X POST http://localhost:8081/query \
  -H 'Content-Type: application/json' \
  -d '{"text": "покажи беспроводные наушники"}'
```

В `degradations` появится пара `reranker` / `unavailable`, а `confidence`
опустится. Отдельный инстанс вместо остановки контейнера нужен, чтобы общий
стенд не мутировался и тесты не зависели от порядка запуска.

## Контракты между сервисами

Шина RabbitMQ — три topic-exchange, все durable:

| Exchange           | Routing key                              | Кто публикует      | Кто читает        |
| ------------------ | ---------------------------------------- | ------------------ | ----------------- |
| `catalog.events`   | `catalog.product.*`                      | catalog-service    | indexing-service  |
| `embedding.jobs`   | `embedding.documents.requested.v1`       | indexing-service   | embedding-service |
| `embedding.events` | `embedding.documents.generated.v1`       | embedding-service  | indexing-service  |

Очередь команд эмбеддинга — quorum, поэтому RabbitMQ нужен не ниже 3.13.

Поиск ходит в Qdrant через алиас `products` — физическая коллекция за ним
называется `products_v1`, что и позволяет переиндексировать каталог в новую
коллекцию и переключить алиас без остановки поиска. Векторы именованные: `dense`
размерности **1024** и `sparse` без IDF. Размерность зафиксирована в двух местах
— `INDEXING_EMBEDDING_DIM` и `EMBEDDING_DIM` — и обязана совпадать, иначе
результат отклоняется как невалидный.

Protobuf-контракты `embedding.v1` и `reranker.v1` принадлежат embedding-service;
research-agent-service держит копию в `contracts/proto` и генерирует из неё свои
стабы. Расхождение копий ловит тест паритета в `e2e/tests/unit`.

## LLM и web-поиск заменены дублями

Детерминированными в стенде сделаны только два внешних провайдера — контейнер
`test-doubles` отдаёт OpenAI-совместимый `/v1/chat/completions` и
Tavily-совместимый `/search`. Всё остальное боевое: реальные модели, реальный
брокер, реальное векторное хранилище. Конвейер проверяется целиком, а сквозные
тесты при этом воспроизводимы и ничего не стоят.

Чтобы включить настоящую модель, поменяйте в `.env` три строки на боевого
OpenAI-совместимого провайдера:

```
LLM_BASE_URL=https://api.deepinfra.com/v1/openai
LLM_MODEL=deepseek-ai/DeepSeek-V4-Flash
LLM_API_KEY=<ваш токен>
```

Сквозные сценарии проверяют контракты платформы, а не формулировки модели, и
проходят в обоих режимах. Но выбор инструментов на живой модели меняется от
прогона к прогону — совпадения ответов не ждите.

## Тесты

У каждого сервиса свой набор, который гоняется изнутри его каталога:

```bash
cd catalog-service
uv sync
uv run pytest
```

Часть наборов поднимает контейнеры через `testcontainers`, так что Docker нужен
и для локального прогона — стенд при этом поднимать не обязательно.

Сквозные тесты живут отдельно и требуют **поднятого стенда**. Они говорят с
платформой только по её публичным контрактам и ничего не пишут в Qdrant напрямую
— точки туда обязан положить конвейер:

```bash
cd e2e
uv sync
uv run pytest -m e2e        # сквозные сценарии
uv run pytest -m contract   # кросс-сервисные контракты
uv run pytest tests/unit    # заглушки и паритет proto, стенд не нужен
```

Если стенд не поднят или не прогрет, набор падает с понятным сообщением о том,
какой компонент не отвечает, а не с таймаутом посреди сценария.

## Разработка

Python 3.12 и [`uv`](https://docs.astral.sh/uv/) — на сервис своё окружение,
общего нет.

Все четыре сервиса построены по Clean Architecture с одинаковым правилом
зависимостей: `presentation → infrastructure → application → domain`,
зависимости направлены внутрь, домен не знает про фреймворки. Правило не
пожелание, а исполняемый инвариант — его проверяет `import-linter`:

```bash
uv run lint-imports
```

Хуки перед коммитом ставятся [`prek`](https://github.com/j178/prek):

```bash
prek install
```

Хуки чистят пробелы и переводы строк, валидируют YAML/TOML/JSON и гоняют
`gitleaks`, так что секреты в репозиторий не попадают. Пароли и ключи приходят
только из `.env` (он под gitignore), в compose-файлах остаются подстановки, и
это отдельно проверяется тестом в `e2e/tests/unit`.

Хуки `ruff` в `prek.toml` ограничены путём `^parser/.*\.py$`, а такого каталога
в репозитории нет — линтер по факту гоняется внутри каждого сервиса через
`uv run ruff check .`, а не на коммите.

Ветки именуются по типу задачи: `feature/...`, `bugfix/...`, `refactor/...` —
строчными буквами через дефис. Коммиты — в формате `тип: описание` на русском
(`feature:`, `fix:`, `docs:`), по одному на логически завершённое изменение.
Pull request'ы тоже на русском и небольшие: один PR — одна задача.

## Структура репозитория

```
catalog-service/          источник истины каталога
indexing-service/         построитель поисковой read-model
embedding-service/        эмбеддинги и реранкинг
research-agent-service/   LLM-агент
e2e/                      тестовые провайдеры и сквозные тесты стенда
docker/postgres/          init-скрипт: роль и база на каждый сервис
docker-compose.yml        единый стенд платформы
docker-compose.cpu.yml    оверлей без GPU
products_catalog_ru.csv   исходные данные для seed (под gitignore)
```
