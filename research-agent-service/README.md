# research-agent-service

LLM-агент, который отвечает на вопросы о товарах и подкрепляет каждый факт
источником: сам решает, чем воспользоваться — поиском по каталогу, ценовым
анализом или внешним вебом, — вызывает инструменты и собирает ответ из того, что
они вернули. Синхронный путь запроса не зависит от RabbitMQ: брокер нужен только
для публикации событий постфактум, через outbox. Агент ходит в
`catalog-service`, `indexing-service` и `embedding-service`, но ничего не
индексирует и цены не считает сам.

## Что умеет агент

Три инструмента, закрытый allowlist (`ToolName`). Имя, пришедшее от модели и не
попавшее в список, не исполняется: модель получает наблюдение
`{"error": "unknown_tool"}` и планирует заново.

| Инструмент            | Что делает                                     | Куда ходит                               |
| --------------------- | ---------------------------------------------- | ---------------------------------------- |
| `product_catalog_rag` | Гибридный поиск товаров по запросу и фасетам    | embedding → Qdrant → embedding → catalog |
| `price_analysis`      | Медиана, бэнды маржи, выбросы по срезу товаров  | catalog `POST /api/v1/analytics/prices`  |
| `web_search`          | Внешний рыночный контекст                       | Tavily или Serper                        |

Цены и маржу агент не считает — этим занят `catalog-service`, инструмент только
передаёт селектор и возвращает готовые числа. Цитата ценового анализа ссылается
на `analysis_ref`: по нему срез воспроизводится в каталоге, то есть число в
ответе проверяемо. Цикл — граф LangGraph из двух узлов: `agent` зовёт модель,
`tools` исполняет запрошенные вызовы и складывает в состояние наблюдения, цитаты
и деградации.

```
POST /query
   ├─ rate limit (Redis)                → 429 + Retry-After, если исчерпан
   ├─ реплей по idempotency_key (Redis) → прежний ответ, если ключ знаком
   ├─ история диалога (PostgreSQL)
   ├─▶ agent ──есть tool_calls?──▶ tools ──▶ agent ──▶ … (LangGraph)
   │      product_catalog_rag ──┬─▶ gRPC EmbedQuery ─▶ embedding-service
   │                            │   Qdrant: dense+sparse, слияние RRF
   │                            │   gRPC Rerank     ─▶ embedding-service
   │                            └─▶ REST by-skus    ─▶ catalog-service
   │      price_analysis ────────▶ REST analytics/prices ─▶ catalog-service
   │      web_search ────────────▶ Tavily / Serper
   ├─ проверка provenance цитат (висячие ссылки выбрасываются)
   └─ одна транзакция: диалог + сообщения + прогон + вызовы + outbox
```

Прогон ограничен доменной политикой `AgentLoopPolicy`: 6 витков, 8 вызовов
инструментов, не больше 2 вызовов одного и того же, 25 секунд на всё. Когда
бюджет кончился, модель вызывается **без** инструментов — это заставляет её
ответить текстом вместо очередного витка. Уверенность считает не модель, а код:
нет цитат — `low`, цитаты с деградациями — `medium`, без деградаций — `high`.

## Быстрый запуск

Сервис поднимается вместе со всей платформой из корня репозитория. Нужен `.env`
(см. `.env.example` там же) — без него пароли подставятся пустыми строками и
стенд не поднимется:

```bash
cp .env.example .env
docker compose up -d --build
docker compose --profile seed run --rm catalog-seed   # наполнить каталог
```

Агент — на `http://localhost:8080`, Swagger — на `/docs`; рядом на
`http://localhost:8081` тот же сервис с намеренно сломанным реранкером
(`agent-api-degraded`). Детерминированными в стенде сделаны только LLM и
web-поиск — оба живут в контейнере `test-doubles`; эмбеддинги, реранкинг,
Qdrant, брокер и каталог боевые.

Локально нужны Python 3.12, [`uv`](https://docs.astral.sh/uv/) и доступные
Postgres, Redis, Qdrant, embedding-service, catalog-service. Свой
`docker-compose.yml` в каталоге сервиса поднимает только Postgres, Redis и
RabbitMQ, остальное ищет по адресам из окружения.

```bash
cd research-agent-service && uv sync && cp .env.example .env
uv run python -m research_agent_service migrate
uv run python -m research_agent_service serve   # uvicorn на 0.0.0.0:8000
uv run python -m research_agent_service relay   # отдельный процесс, дренаж outbox
```

## API

```bash
curl -X POST http://localhost:8080/query \
  -H 'Content-Type: application/json' \
  -H 'X-Client-Principal: demo-user' \
  -d '{"text": "подбери беспроводные наушники и посчитай маржинальность",
       "idempotency_key": "demo-1"}'
```

Тело: `text` (1–4000 символов), `locale` (по умолчанию `ru`), `conversation_id`,
`idempotency_key`, `filters`. Незнакомые поля отклоняются. В `filters` разрешены
только индексируемые фасеты — `category`, `brand`, `supplier`, `price_min`,
`price_max`, `in_stock`, `min_rating`, `margin_min`, `margin_max`; они
валидируются, но до поиска не доходят (см. «Грабли»). Заголовки необязательны:
`X-Client-Principal` (по умолчанию `anonymous`, от него считаются лимит и ключ
идемпотентности), `X-Trace-Id`, `X-Correlation-Id` — последние два попадают в
логи, конверт события и его headers.

Ответ — `200` такой формы:

```json
{
  "agent_run_id": "0197f0c1-6b2a-7c31-9a4e-2f8d1c0b5e77",
  "conversation_id": "0197f0c1-6b2a-7c31-9a4e-2f8d1c0b5e78",
  "status": "completed",
  "answer": "Товары: SKU-1001, SKU-1002. Ценовой анализ pa-3f9c2a17be04d5c8: …",
  "citations": [
    {"source_type": "product", "ref": "SKU-1001", "title": "Гарнитура X",
     "snippet": "Беспроводная гарнитура…", "position": 0, "score": "0.87"}
  ],
  "used_tools": ["product_catalog_rag", "price_analysis"],
  "confidence": "high",
  "degradations": [],
  "usage": {"prompt_tokens": 16, "completion_tokens": 8, "total_tokens": 24},
  "latency_ms": 1840
}
```

`status` — `completed`, если деградаций не было, и `degraded`, если были.
`source_type` бывает `product`, `price_analysis` и `web`; `score` приходит
строкой, чтобы не терять точность на float.

```bash
curl 'http://localhost:8080/queries?status=degraded&limit=20&offset=0'
curl http://localhost:8080/queries/0197f0c1-6b2a-7c31-9a4e-2f8d1c0b5e77
curl -X POST http://localhost:8080/queries/0197f0c1-.../feedback \
  -H 'Content-Type: application/json' -d '{"rating": "down", "labels": ["recall"]}'
```

Список принимает фильтры `conversation_id` и `status`, `limit` 1..100 и
`offset`. Детали прогона отдают `usage`, `degradations`, `loop_steps` и
`error_code`, на неизвестный id — `404`. Обратная связь принимает `rating`
(`up`/`down`), необязательные `reason` и `labels`, и отвечает `204`. Ещё есть
`GET /health` (процесс жив), `GET /ready` (`200`, если отвечают Postgres и
Redis, иначе `503`) и `GET /metrics` с метриками Prometheus. Ошибки приходят в
едином формате `{"error": ..., "detail": ...}`:

| Код   | `error`           | Когда                                                        |
| ----- | ----------------- | ------------------------------------------------------------ |
| `404` | `not_found`       | Прогона с таким id нет                                        |
| `422` | `invalid_request` | Доменная валидация: пустой текст, длиннее 4000, `min > max`   |
| `429` | `rate_limited`    | Больше 60 запросов за 60 с на принципала; отдаётся `Retry-After` |
| `502` | `query_failed`    | Оркестратор упал; в `detail` — id прогона, он записан как `failed` |

## Подключить настоящую модель

LLM подключается как **OpenAI-совместимый** провайдер с кастомным `base_url` —
никакого Anthropic SDK, под капотом `ChatOpenAI` из `langchain-openai`. В стенде
адрес берётся из корневого `.env`, поменять нужно три строки:

```
LLM_BASE_URL=https://api.deepinfra.com/v1/openai
LLM_MODEL=deepseek-ai/DeepSeek-V4-Flash
LLM_API_KEY=<ваш токен>
```

Они прокидываются в `RESEARCH_AGENT_LLM__BASE_URL`, `__MODEL` и `__API_KEY`; вне
стенда задавайте эти переменные напрямую — умолчания в коде уже указывают на
DeepInfra, не хватает только ключа. Дубль планирует вызовы по фиксированным
маркерам в тексте («найди», «маржин», «рынк»), живая модель решает сама: набор
инструментов и формулировки поплывут от прогона к прогону, а `usage` перестанет
быть константой. Гарантии платформы — исполнение вызова, provenance цитат,
отражение деградаций, идемпотентность — сохраняются, на них и построены сквозные
тесты. Два поля не отправляются, пока не заданы явно: `LLM__SERVICE_TIER`
(расширение OpenAI) и `LLM__ENABLE_THINKING` (уезжает в `chat_template_kwargs`,
понимают vLLM-совместимые) — чужой провайдер вправе отвергнуть незнакомое поле.

## Реранкер может отвалиться — поиск продолжит работать

Пайплайн `product_catalog_rag`: `EmbedQuery` по gRPC отдаёт dense- и
sparse-вектор запроса; Qdrant получает **один** запрос с двумя prefetch по
именованным векторам `dense` и `sparse` и сливает их серверным **RRF**;
кандидаты дедуплицируются по `product_id`; `Rerank` по gRPC переставляет их
cross-encoder'ом и отдаёт top-8; цены, остатки и маржа берутся из
`catalog-service` по SKU, потому что payload Qdrant для этого не авторитетен.
Фильтр всегда несёт `must_not: is_deleted == true`, фасеты инструмента ложатся в
`must`; записей не делается, векторы обратно не тянутся.

Реранкер ответил `UNIMPLEMENTED`, `UNAVAILABLE` или `DEADLINE_EXCEEDED` — клиент
переводит это в `RerankerUnavailable`, пайплайн берёт первые 8 в порядке RRF,
проставляет цитатам `score: null` и добавляет деградацию
`reranker / unavailable`. Ответ приходит, `confidence` опускается до `medium`,
статус прогона — `degraded`. Прочие коды gRPC пробрасываются наружу: это не
деградация, а поломка. Каталог недоступен — деградация `catalog / unavailable`,
товары собираются из payload Qdrant с пометкой `price_authoritative: false`.
Web-поиск на любой HTTP-ошибке возвращает пустой список, а не исключение. Отказ
любого инструмента превращается в наблюдение `{"error": "tool_failed"}` — модель
это видит и может перепланировать, вместо того чтобы получить исключение в
графе.

Проверить деградацию, ничего не ломая в общем стенде, можно на порту `8081`: у
`agent-api-degraded` переменная `RESEARCH_AGENT_RERANKER_GRPC_TARGET` смотрит в
закрытый порт, поэтому gRPC отвечает `UNAVAILABLE`. Отдельный инстанс нужен,
чтобы тесты не зависели от порядка запуска.

## Конфигурация

Всё читается pydantic-settings с префиксом `RESEARCH_AGENT_`, плюс `.env` в
рабочем каталоге. Незнакомые переменные игнорируются.

| Переменная                             | Зачем                                             | Дефолт                     |
| -------------------------------------- | ------------------------------------------------- | -------------------------- |
| `RESEARCH_AGENT_SERVICE_NAME`          | Имя сервиса в ресурсе трейсинга                    | `research-agent-service`   |
| `RESEARCH_AGENT_LOG_LEVEL`             | Уровень JSON-логов                                 | `INFO`                     |
| `RESEARCH_AGENT_DATABASE_URL`          | PostgreSQL, `postgresql+asyncpg://…`               | локальный `research_agent` |
| `RESEARCH_AGENT_REDIS_URL`             | Redis: лимиты и идемпотентность                    | `redis://localhost:6379/0` |
| `RESEARCH_AGENT_RABBITMQ_DSN`          | Брокер; нужен только relay'ю                       | `amqp://guest:guest@localhost:5672/` |
| `RESEARCH_AGENT_EMBEDDING_GRPC_TARGET` | Адрес `EmbedQuery`                                 | `localhost:50051`          |
| `RESEARCH_AGENT_RERANKER_GRPC_TARGET`  | Адрес `Rerank` — отдельно, реранкер живёт сам по себе | `localhost:50051`       |
| `RESEARCH_AGENT_EMBEDDING_DEADLINE_S`  | Дедлайн вызова эмбеддинга                          | `1.5`                      |
| `RESEARCH_AGENT_RERANKER_DEADLINE_S`   | Дедлайн вызова реранкинга                          | `5.0`                      |
| `RESEARCH_AGENT_QDRANT_URL`            | Qdrant, только чтение                              | `http://localhost:6333`    |
| `RESEARCH_AGENT_QDRANT_COLLECTION`     | Коллекция или её алиас                             | `products`                 |
| `RESEARCH_AGENT_CATALOG_BASE_URL`      | REST каталога                                      | `http://localhost:8000`    |
| `RESEARCH_AGENT_WEB_SEARCH_PROVIDER`   | `tavily` или `serper`                              | `tavily`                   |
| `RESEARCH_AGENT_WEB_SEARCH_API_KEY`    | Ключ провайдера                                    | пусто                      |
| `RESEARCH_AGENT_WEB_SEARCH_BASE_URL`   | Свой адрес того же API; пусто — публичный эндпоинт | пусто                      |
| `RESEARCH_AGENT_RELAY_INTERVAL_S`      | Пауза между дренажами outbox                       | `1.0`                      |
| `RESEARCH_AGENT_RELAY_BATCH_SIZE`      | Размер партии дренажа                              | `100`                      |
| `RESEARCH_AGENT_OTLP_ENDPOINT`         | OTLP-коллектор; пусто — трейсинг выключен          | пусто                      |

Настройки LLM вложенные, разделитель — двойное подчёркивание, поэтому
`RESEARCH_AGENT_LLM__MODEL` кладётся в поле `model` объекта `llm`:

| Переменная                            | Зачем                                            | Дефолт                                |
| ------------------------------------- | ------------------------------------------------ | ------------------------------------- |
| `RESEARCH_AGENT_LLM__BASE_URL`        | OpenAI-совместимый эндпоинт                       | `https://api.deepinfra.com/v1/openai` |
| `RESEARCH_AGENT_LLM__MODEL`           | Имя модели у провайдера                           | `deepseek-ai/DeepSeek-V4-Flash`       |
| `RESEARCH_AGENT_LLM__API_KEY`         | Токен; заглушка `unset` не сработает              | `unset`                               |
| `RESEARCH_AGENT_LLM__TEMPERATURE`     | Температура                                       | `0.0`                                 |
| `RESEARCH_AGENT_LLM__MAX_TOKENS`      | Потолок ответа                                    | `4096`                                |
| `RESEARCH_AGENT_LLM__TIMEOUT`         | Таймаут вызова провайдера                         | `60.0`                                |
| `RESEARCH_AGENT_LLM__MAX_RETRIES`     | Ретраи клиента к провайдеру                       | `3`                                   |
| `RESEARCH_AGENT_LLM__SERVICE_TIER`    | Расширение OpenAI; пусто — не отправляется        | пусто                                 |
| `RESEARCH_AGENT_LLM__ENABLE_THINKING` | Флаг vLLM-совместимых; не задан — не отправляется | не задан                              |

Дедлайны gRPC рассчитаны на GPU. На CPU те же модели отвечают в разы медленнее,
и умолчания срываются в `DEADLINE_EXCEEDED`, то есть в деградацию на каждом
запросе — поднимайте вместе с переходом на CPU.

## Как устроен код

- `domain/` — сущности, value objects, политика цикла; только stdlib.
- `application/` — use cases, прикладные сервисы, порты, конверты событий.
- `infrastructure/` — адаптеры: `agent` (LangGraph), `grpc`, `qdrant`, `redis`,
  `db`, `catalog`, `websearch`, `messaging`, `outbox`, `observability`.
- `presentation/` — `api` (FastAPI), `schemas` (pydantic), `messaging`, `cli`.
- `bootstrap.py` и `main.py` — composition root и ASGI-точка входа.

Зависимости направлены внутрь:
`presentation → infrastructure → application → domain`. Домен не знает ни про
фреймворки, ни про pydantic; прикладной слой общается с внешним миром только
через порты. Это не договорённость, а исполняемый инвариант — три контракта
`import-linter` в `pyproject.toml` запрещают домену и прикладному слою
langgraph, fastapi, sqlalchemy, redis, grpc, httpx, pydantic и прочее и
фиксируют направление слоёв. То же дублируется в ruff через
`flake8-tidy-imports`, с исключениями для инфраструктуры, presentation и
composition root. Проверка — `uv run lint-imports`.

## Надёжность

**Идемпотентность.** `idempotency_key` из тела запроса вместе с
`client_principal` дают ключ `idem:{principal}:{key}` в Redis, где лежит id
прогона, TTL — сутки. Повтор читает прогон и его ответное сообщение из Postgres
и возвращает их без обращения к модели; реплеятся только завершённые прогоны.
Ключ хранится и в колонке `agent_runs.idempotency_key`, но дедупликацию делает
Redis, отдельной таблицы под это нет. Кроме этого ключа Redis держит только
счётчик `ratelimit:{principal}` с TTL на фиксированное окно — ни ответы, ни
эмбеддинги не кешируются.

**Transactional Outbox.** Диалог, сообщения, прогон, вызовы инструментов и
запись outbox коммитятся одной транзакцией; провалившийся прогон пишется так же,
с событием `agent.query.failed.v1`. В брокер write-path не пишет вообще —
отдельный процесс `agent-relay` выбирает неопубликованные строки
`FOR UPDATE SKIP LOCKED`, публикует их в durable topic-exchange
`research-agent.events` с `routing_key == event_type` и `message_id == id`
строки, затем проставляет `published_at`. Ошибка публикации — экспоненциальный
бэкофф (`2^attempts`, потолок 300 с, джиттер до 10%); после 10 попыток строка
уходит в карантин `failed_at` и перестаёт мешать очереди. Публикуются четыре
события: `agent.query.completed.v1`, `agent.query.failed.v1`,
`agent.feedback.received.v1` и `agent.evaluation.requested.v1` — последнее
дополнительно к негативной оценке. `event_id` совпадает с id строки outbox
(uuidv7), `trace_id` и `correlation_id` едут и в конверте, и в headers.

**Provenance.** Перед сохранением цитаты проверяются: `ref` обязан входить во
множество реально полученных фактов своего типа — SKU для `product`, URL для
`web`, `analysis_ref` для `price_analysis`. Висячие ссылки выбрасываются, а в
ответе появляется деградация `citations / dangling_dropped`. Заголовок и сниппет
web-результата дополнительно чистятся от HTML, содержимого `script`/`style` и
управляющих символов и режутся до 2000 символов; URL берётся как есть.

## Разработка и тесты

```bash
uv sync
uv run ruff format . && uv run ruff check .
uv run lint-imports
uv run pytest tests/unit      # ничего внешнего не нужно
uv run pytest -m integration  # Postgres и RabbitMQ в testcontainers, нужен Docker
uv run pytest -m contract     # конверты событий против JSON Schema
uv run pytest -m e2e          # путь запроса целиком на реальном Postgres
uv run pytest --cov           # порог покрытия — 90% с ветками
```

Маркеры строгие (`--strict-markers`), порядок тестов случайный из-за
pytest-randomly. В `tests/e2e` поднимается настоящее приложение с настоящими use
cases, оркестратором и Postgres; заглушены только модель (`bind_tools`
возвращает себя, `ainvoke` отдаёт очередь заготовленных `AIMessage`) и источники
данных инструментов.

Миграции — Alembic (`uv run alembic revision --autogenerate -m "…"`, затем
`upgrade head`), одна ревизия `0001_baseline`, шесть таблиц: `conversations`,
`messages`, `agent_runs`, `tool_calls`, `feedback`, `outbox_events`. Внешние
ключи объявлены `DEFERRABLE INITIALLY DEFERRED` — иначе агрегаты не удалось бы
записать одним коммитом в произвольном порядке. В контейнере миграции накатывает
entrypoint, но только у роли с `RUN_MIGRATIONS=1` (в стенде это `agent-api`) —
иначе несколько процессов полезли бы в alembic одновременно.

Сквозные тесты платформы живут в корневом `e2e/` и требуют поднятого стенда:
`cd e2e && uv sync && uv run pytest -m e2e`. Они говорят с агентом по HTTP и
проверяют контракты платформы, а не формулировки модели: затребованный
инструмент исполнен, у факта есть цитата нужного типа с валидной ссылкой,
деградация отражена в ответе, повтор по ключу вернул тот же `agent_run_id`.
Поэтому набор проходит и на дубле, и на живой модели. gRPC-стабы генерируются из
копий `.proto` в `contracts/proto` командой `sh contracts/proto/generate.sh`;
оригиналы принадлежат embedding-service, расхождение ловит тест паритета в
`e2e/tests/unit`.

## Грабли

**Дедлайны на CPU.** Самая частая причина «почему у меня всё время `degraded`» —
реранкер не укладывается в 5 секунд. Поднимайте
`RESEARCH_AGENT_RERANKER_DEADLINE_S`; в стенде это делает
`docker-compose.cpu.yml`.

**Пустой `LLM__API_KEY`.** Умолчание — строка `unset`, а не пустое значение:
клиент OpenAI не собирается с пустым ключом. Провайдер на таком ключе ответит
401, и каждый запрос уйдёт в `502 query_failed`.

**`migrate` из чужого каталога.** CLI открывает `alembic.ini` по относительному
пути — команду нужно запускать из корня сервиса.

**Отказ эмбеддинга — не деградация.** У `RerankerUnavailable` и
`CatalogUnavailable` обработка есть, у `EmbedQuery` нет: его сбой валит весь
вызов инструмента в `tool_failed`. Без вектора запроса искать всё равно негде.

**`filters` из тела запроса до Qdrant не доезжают.** Схема их принимает и
доменный `QueryFilters` валидирует, но дальше `Query.filters` нигде не читается:
в промпт уходит только `query.text`. Фасеты поиска берутся из аргументов
инструмента, которые заполняет модель. Хотите гарантированно сузить срез —
пишите категорию или бренд в сам текст запроса.

**Товары, которых нет в каталоге, теряют цитаты.** Если `by-skus` вернул их в
`missing_skus`, они выпадают из результата, и ссылка на них будет отброшена как
висячая — даже когда Qdrant их нашёл.
