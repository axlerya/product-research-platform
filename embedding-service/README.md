# embedding-service

Считает эмбеддинги и реранкинг для всей платформы. Модель BGE-M3 (`BAAI/bge-m3`)
даёт dense-вектор на 1024 компонента и sparse-веса за один прогон, кросс-энкодер
`BAAI/bge-reranker-v2-m3` переупорядочивает кандидатов по релевантности. Модель
загружается один раз в процесс, и оба транспорта — gRPC и RabbitMQ — работают
поверх одного экземпляра.

Соседи не держат весов у себя: indexing-service заказывает векторы командой в
шину, research-agent-service ходит за вектором запроса и реранкингом по gRPC.

## Два транспорта в одном процессе, потому что у нагрузок разная цена ошибки

Поисковый запрос ждёт живой человек: тут нужен синхронный вызов с дедлайном, и
лучше отказать сразу, чем ответить через минуту. Документы индексируются
пачками, ответ никто не ждёт в реальном времени, зато нельзя терять команды при
перезапуске — это работа для очереди с подтверждениями и ретраями.

Отсюда деление: `EmbedQuery`/`EmbedQueries`/`Rerank` — gRPC на `50051`,
документы — консюмер `embedding.documents.requests`. Внутри батчер держит две
полосы: `QUERY` собирается 5 мс и обслуживается первой, `DOCUMENT` копит батч 50
мс ради пропускной способности.

Реранкер слушает тот же порт, но это отдельная модель с отдельным жизненным
циклом. Разница видна по кодам ответа:

- `RERANKER_ENABLED=false` — `RerankerService` вообще не регистрируется,
  `Rerank` отвечает `UNIMPLEMENTED`;
- включён, но провайдер не собрался или прогрев упал — сервис зарегистрирован,
  health отдаёт `NOT_SERVING`, `Rerank` отвечает `UNAVAILABLE`;
- эмбеддинги в обоих случаях продолжают работать.

Сбой реранкера ловится в двух местах: при сборке зависимостей
(`bootstrap.build_deps`) и при прогреве (`main._prepare_reranker`) — оба пишут
warning и идут дальше.

## Место в платформе

```
                              команда: embedding.jobs / embedding.documents.requested.v1
   indexing-service  ───────────────────────────────────────────────▶  ┌───────────────────┐
                     ◀───────────────────────────────────────────────  │ embedding-service │
                              событие: embedding.events / embedding.documents.generated.v1
                                                                       │  BGE-M3           │
   research-agent-service ──── gRPC :50051  EmbedQuery ──────────────▶  │  bge-reranker-v2  │
                          ──── gRPC :50051  Rerank ────────────────────▶└───────────────────┘
```

catalog-service с эмбеддингами не общается: он публикует события каталога, а
команду на векторизацию собирает уже indexing-service.

## Первый запуск скачивает модели и занимает минуты

Общий стенд из корня репозитория (нужен `.env`, см. `.env.example` в корне):

```bash
docker compose up -d --build embedding
curl -fsS http://localhost:8010/ready
```

Здесь сервис называется `embedding`, собирается из `docker/Dockerfile.gpu` и
резервирует одну NVIDIA-карту. Порты наружу: `50051` (gRPC) и `8010` (ops,
внутри `8000`). Реранкер в общем стенде включён (`RERANKER_ENABLED: "true"`).

Без GPU поверх базового файла кладётся оверлей — он переключает сборку на
`docker/Dockerfile.cpu`, ставит `EMBEDDING_DEVICE=cpu`/`RERANKER_DEVICE=cpu` с
точностью `fp32`, снимает резервирование GPU через `deploy: !reset null` и
расширяет дедлайны агента (`RESEARCH_AGENT_EMBEDDING_DEADLINE_S=10`,
`RESEARCH_AGENT_RERANKER_DEADLINE_S=30`):

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build
```

Изолированный стенд самого сервиса (`embedding-service/docker-compose.yml`)
поднимает RabbitMQ рядом и выбирает провайдер профилем. Порт ops здесь `8000`,
реранкер не включён:

```bash
cd embedding-service
docker compose --profile fake up --build   # детерминированный провайдер, без torch и весов
docker compose --profile cpu  up --build   # реальная BGE-M3 на CPU
docker compose --profile gpu  up --build   # реальная BGE-M3 на CUDA
```

Локально через `uv`:

```bash
cd embedding-service
uv sync                                        # без torch — хватит для FAKE и тестов
uv sync --extra embedding --extra reranking    # реальные модели
cp .env.example .env
uv run python -m embedding_service serve
```

Оба extra объявляют одно и то же (`FlagEmbedding` + `transformers>=4.44,<5`),
образы ставят только `--extra embedding` — реранкер берёт `FlagReranker` из того
же пакета.

**Про первый старт.** Веса тянутся с HuggingFace в
`HF_HOME=/app/.cache/huggingface`; в корневом compose под это смонтирован том
`hf_cache`, в изолированном — `hf-cache`. Две модели весят порядка 4.6 ГБ,
поэтому healthcheck в корневом стенде даёт `start_period: 900s`. Пока модель не
прогрета, `/ready` отдаёт 503 и gRPC health — `NOT_SERVING`: сервис поднимает
readiness только после успешного прогона проб-текста через `warmup`. Снесёте том
— качать придётся заново.

Быстрая проверка обвязки без весов: `EMBEDDING_PROVIDER_MODE=deterministic` (и
`RERANKER_PROVIDER_MODE=deterministic`) — вектор выводится из sha256 текста,
стабилен между перезапусками, torch не нужен.

## Контракты

### gRPC, `contracts/proto/`

`embedding.v1.EmbeddingService`:

| Метод | Запрос | Ответ |
| --- | --- | --- |
| `EmbedQuery` | `text`, `request_id` (опц.) | `embedding` (`dense`, `sparse`, `token_count`), `model_version`, `dim` |
| `EmbedQueries` | `texts[]`, `request_id` (опц.) | `embeddings[]` в порядке `texts`, `model_version`, `dim` |

`reranker.v1.RerankerService`:

| Метод | Запрос | Ответ |
| --- | --- | --- |
| `Rerank` | `query`, `documents[]` (`id`, `text`), `top_n` (опц.), `return_documents` | `results[]` (`id`, `index`, `score`, `text`), `model_version` |

`index` в ответе — исходная позиция документа во входе; `text` возвращается
только при `return_documents=true`. Сортировка детерминирована: по убыванию
`score`, при равенстве — по возрастанию `index`. `model_version` — водяной знак
модели вида `BAAI/bge-m3@unknown|pool=cls|norm=1|dim=1024`; его смена означает,
что старые векторы несопоставимы с новыми.

Ошибки: невалидный вход — `INVALID_ARGUMENT` (fail-fast на весь вызов, батч
целиком), переполнение очереди — `RESOURCE_EXHAUSTED`, таймаут инференса —
`DEADLINE_EXCEEDED`, модель не готова — `UNAVAILABLE`. Вызов без запаса времени
тоже отклоняется: если до дедлайна осталось меньше 5 мс, сервис не начинает
инференс.

Стабы генерируются скриптом `sh contracts/proto/generate.sh` в
`embedding_service/infrastructure/grpc/_generated` (руками не правятся, из линта
исключены).

### RabbitMQ, `contracts/rabbitmq/`

**Команда** приходит в exchange `embedding.jobs` (topic, durable) с routing key
`embedding.documents.requested.v1`. Читается tolerant: незнакомые поля
игнорируются, обязательны `event_id`, `event_type`, `occurred_at`, `producer` и
`data` с `request_id`, `return_dense`, `return_sparse`, непустым `items[]`
(`text_id`, `text`).

**Результат** публикуется в `embedding.events` (topic, durable) с routing key
`embedding.documents.generated.v1`, `producer: "embedding-service"`,
`aggregate_id` = `request_id`. В `data.results[]` каждый элемент либо
`status: "ok"` с `dense`/`sparse` (по запрошенным `return_*`) и `token_count`,
либо `status: "error"` с кодом из закрытого набора: `EMPTY_TEXT`,
`TEXT_TOO_LONG`, `TOKENS_EXCEEDED`, `INFERENCE_FAILED`. `trace_id` и
`correlation_id` переносятся из команды.

Одна битая позиция не роняет батч — она едет ошибкой, остальные считаются. А вот
структурный дефект команды (пустой батч, слишком много текстов, превышение
общего размера) — это отравленное сообщение, оно уходит в DLQ целиком.

Схемы JSON Schema и примеры лежат в `contracts/rabbitmq/`; контрактные тесты
валидируют примеры против схем.

## Проверка живости

Ops-плоскость поднимается тем же процессом (порт из `EMBEDDING_OPS_HTTP_PORT`,
наружу `8010` в корневом стенде):

| Маршрут | Что означает |
| --- | --- |
| `/health` | пинг RabbitMQ с таймаутом 5 с — процесс жив и видит брокер |
| `/ready` | 200 `{"ready":true}` только после успешного прогрева модели, иначе 503 |
| `/reranker/ready` | появляется только при `RERANKER_ENABLED=true`; готовность реранкера отдельно от `/ready` |
| `/metrics` | реестр Prometheus |

Разница между `/health` и `/ready` практическая: `/health` может быть зелёным,
пока модель ещё грузится, и трафик на такой инстанс пускать рано. В контейнере
healthcheck смотрит именно на `/ready`.

gRPC-рефлексия включена, так что `grpcurl` работает без `.proto`:

```bash
grpcurl -plaintext localhost:50051 list
grpcurl -plaintext -d '{"text":"беспроводные наушники"}' \
  localhost:50051 embedding.v1.EmbeddingService/EmbedQuery
grpcurl -plaintext -d '{"query":"наушники","documents":[{"id":"p1","text":"беспроводные наушники"}],"top_n":1}' \
  localhost:50051 reranker.v1.RerankerService/Rerank
```

Ещё две команды CLI, чтобы не поднимать сервер целиком:
`uv run python -m embedding_service describe-model` печатает
`model_version`/устройство/точность, `uv run python -m embedding_service warmup`
прогревает модель и выходит.

Метрики (`embedding_*`, `reranker_*`) регистрируются в реестре и отдаются на
`/metrics`, но кодом инференса пока не обновляются — под дашборд их ещё нужно
проинструментировать.

## Конфигурация

Настройки читаются из окружения и `.env` (pydantic-settings). Обязательных
переменных нет — у всего есть дефолт; на практике задавать нужно
`EMBEDDING_RABBITMQ_DSN` и, если работаете с реальной моделью, устройство с
точностью.

**Эмбеддинги, префикс `EMBEDDING_`:**

| Переменная | Назначение | Дефолт |
| --- | --- | --- |
| `RABBITMQ_DSN` | адрес брокера | `amqp://guest:guest@localhost:5672/` |
| `GRPC_HOST` / `GRPC_PORT` | адрес gRPC-сервера | `0.0.0.0` / `50051` |
| `OPS_HOST` / `OPS_HTTP_PORT` | адрес ops-плоскости | `0.0.0.0` / `8000` |
| `PROVIDER_MODE` | `bge_m3` или `deterministic` (FAKE) | `bge_m3` |
| `MODEL` / `REVISION` | имя весов и ревизия (пусто → `unknown` в `model_version`) | `BAAI/bge-m3` / пусто |
| `DIM` | размерность dense-вектора | `1024` |
| `POOLING` / `NORMALIZED` | пулинг и L2-нормировка (входят в `model_version`) | `cls` / `true` |
| `DEVICE` | `auto` (cuda→cpu), `cpu`, `cuda` | `auto` |
| `PRECISION` | `fp32`, `fp16`, `bf16`; на CPU всегда `fp32`, `bf16` без Ampere откатывается в `fp16` | `fp16` |
| `MAX_BATCH_SIZE` | потолок склеенного батча | `16` |
| `BATCH_WAIT_MS` / `QUERY_BATCH_WAIT_MS` | окно накопления документов и запросов | `50` / `5` |
| `MAX_CONCURRENT_INFERENCES` | одновременных прогонов модели | `1` |
| `MAX_QUEUE_SIZE` | глубина очереди ожидания, дальше `RESOURCE_EXHAUSTED` | `256` |
| `INFERENCE_TIMEOUT_S` | таймаут одного прогона | `30` |
| `PREFETCH_COUNT` | QoS консюмера | `8` |
| `DOC_MAX_TEXTS` / `DOC_MAX_TEXT_CHARS` | лимиты документного батча | `256` / `32000` |
| `DOC_MAX_TOKENS` / `DOC_MAX_TOTAL_BYTES` | лимиты документного батча | `8192` / `4194304` |
| `QUERY_MAX_TEXTS` / `QUERY_MAX_TEXT_CHARS` | лимиты батча запросов | `32` / `8000` |
| `QUERY_MAX_TOKENS` / `QUERY_MAX_TOTAL_BYTES` | лимиты батча запросов | `8192` / `262144` |
| `MAX_ATTEMPTS` | доставок до отправки в DLQ | `5` |
| `RETRY_TTL_MS` | выдержка в retry-очереди | `30000` |
| `GRACEFUL_TIMEOUT` | окно дренажа при остановке | `30` |
| `SERVICE_NAME` | имя сервиса для наблюдаемости | `embedding-service` |

`EMBEDDING_CPU_FALLBACK` и `EMBEDDING_OTLP_ENDPOINT` объявлены в настройках, но
в composition root пока не подключены — менять их бессмысленно.

**Реранкер, префикс `RERANKER_`:**

| Переменная | Назначение | Дефолт |
| --- | --- | --- |
| `ENABLED` | включает `RerankerService`; выключен → `Rerank` = `UNIMPLEMENTED` | `false` |
| `PROVIDER_MODE` | `bge_reranker` или `deterministic` | `bge_reranker` |
| `MODEL` / `REVISION` | веса кросс-энкодера | `BAAI/bge-reranker-v2-m3` / пусто |
| `NORMALIZED` | нормировать ли скор в `[0, 1]` | `true` |
| `DEVICE` / `PRECISION` | устройство и точность (независимо от эмбеддингов) | `auto` / `fp16` |
| `MAX_BATCH_SIZE` | размер чанка пар, отдаваемого модели | `32` |
| `INFERENCE_TIMEOUT_S` | таймаут одного чанка | `10` |
| `MAX_CONCURRENT_INFERENCES` | одновременных прогонов | `1` |
| `MAX_DOCUMENTS` | потолок кандидатов в запросе | `256` |
| `MAX_QUERY_CHARS` / `MAX_DOCUMENT_CHARS` | лимиты длины | `8000` / `32000` |
| `MAX_TOTAL_BYTES` | потолок размера запроса | `4194304` |

## Как устроен код

Clean Architecture, четыре слоя, зависимости смотрят внутрь:

```
domain/          value objects и доменные сервисы; ничего внешнего не знает
application/     use cases (EmbedDocuments, EmbedQuery, EmbedQueries,
                 RerankDocuments, WarmupModel, DescribeModel) и порты
infrastructure/  провайдеры моделей, батчер, конфиг, метрики, gRPC-стабы
presentation/    gRPC-сервисеры, консюмер, ops-маршруты, CLI
bootstrap.py     composition root — единственное место, знающее все слои
```

Модель прячется за портом `EmbeddingProvider` (и `RerankerProvider`), поэтому
use cases одинаково работают с реальными весами и с детерминированным дублем.
`BatchingEmbeddingProvider` — декоратор того же порта: он склеивает конкурентные
вызовы, ограничивает параллелизм семафором и раздаёт результаты строго в порядке
входа.

Правило зависимостей не на честном слове, а исполняемое: `import-linter`
запрещает `domain` и `application` импортировать `FlagEmbedding`, `torch`,
`transformers`, `grpc`, `faststream`, `pydantic`, `opentelemetry` и требует
направления `application → domain`. Плюс ruff (`TID251`) банит те же импорты вне
`infrastructure`/`presentation`.

## Что происходит с командой, если модель упала

Топология собирается сама при старте консюмера — лестница
`main → retry → requeue → parking`:

- `embedding.documents.requests` — основная очередь, **quorum** (поэтому в
  стенде RabbitMQ не ниже 3.13), dead-letter в `embedding.retry`;
- `embedding.documents.requests.retry` — держит сообщение `RETRY_TTL_MS` и по
  истечении TTL перекладывает его в `embedding.requeue`, откуда оно возвращается
  в основную очередь;
- `embedding.documents.requests.dlq` — терминальная парковка для ручного
  разбора.

Приватные exchange (`embedding.retry`, `embedding.requeue`, `embedding.parking`)
держат ретрай-трафик внутри сервиса и не задевают других потребителей
`embedding.jobs`.

Решение по каждому сообщению принимает `dispatch`:

- схема не разобралась или ошибка постоянная — в парковку и `ack` (гонять
  отравленное сообщение по кругу бессмысленно);
- успех — сначала публикация результата с подтверждением брокера, и только потом
  `ack` входящей команды;
- транзиентная ошибка — `reject` без requeue, то есть уход на retry-лестницу;
  когда `x-death.count` дорастает до `MAX_ATTEMPTS`, сообщение паркуется.

Порядок «публикация → ack» означает, что при падении между ними команда переедет
заново. Это безопасно: эмбеддинг — чистая функция от текста, повторный прогон
даёт тот же результат, а `request_id` в событии позволяет потребителю
сопоставить дубль. Собственного журнала обработанных сообщений сервис не ведёт.

Отдельно про OOM: при `torch.cuda.OutOfMemoryError` батч чистит кэш аллокатора и
дробится пополам, рекурсивно, с сохранением порядка. Если OOM повторяется на
одном тексте — ошибка уходит наверх.

## Разработка

```bash
uv sync                              # dev-зависимости, без torch
uv run pytest                        # весь набор
uv run pytest -m "not slow and not nightly"
uv run pytest --cov                  # порог покрытия 90%, branch coverage
uv run ruff check .
uv run lint-imports                  # контракты слоёв
```

Python 3.12, длина строки 80 символов (Google Python Style Guide). Разработка
ведётся через TDD.

Тесты разложены по слоям: `tests/unit` (домен, application, инфраструктура,
presentation), `tests/integration` (gRPC-сервер в процессе и консюмер через
`TestRabbitBroker` — Docker не нужен), `tests/contract` (proto, JSON Schema,
границы версий зависимостей), `tests/performance`.

Маркеры объявлены строго (`--strict-markers`): `integration`, `contract`,
`slow`, `nightly`, `performance`. Весь набор проходит без GPU и без скачивания
весов — единственный тест на реальной модели помечен `slow`/`nightly` и сам себя
пропускает, если `FlagEmbedding` не установлен.

## Грабли

**Размерность обязана совпадать с indexing-service.** `EMBEDDING_DIM` и
`INDEXING_EMBEDDING_DIM` — 1024 в обоих сервисах. Разойдутся — indexing отклонит
результат как невалидный и создаст коллекцию под другую размерность. Схема
события фиксирует `dim` константой 1024, так что контрактный тест поймает
расхождение раньше стенда.

**`EMBEDDING_DEVICE=cuda` без CUDA — это отказ старта.** Провайдер поднимает
`ProbeFailed`, readiness не открывается, контейнер остаётся нездоровым. `auto` в
такой ситуации молча уедет на CPU: считать будет, но в разы медленнее, и
дедлайны агента, рассчитанные на GPU, начнут срываться — для этого и существует
`docker-compose.cpu.yml` с расширенными дедлайнами.

**Кэш моделей занимает место и время.** Две модели — порядка 4.6 ГБ на томе.
Удалённый том означает повторную загрузку и новые 900 секунд ожидания
готовности.

**Реранкер по умолчанию выключен.** Если `Rerank` отвечает `UNIMPLEMENTED` —
проверьте `RERANKER_ENABLED`. В изолированном
`embedding-service/docker-compose.yml` он не включён ни в одном профиле; включён
он только в корневом стенде.

**`transformers` жёстко ограничен снизу пятой мажорной версии.** FlagEmbedding
зовёт у токенайзера `prepare_for_model`, которого в 5.x уже нет. Снимете границу
— эмбеддинги продолжат работать, а прогрев реранкера упадёт, и реранкинг будет
молча деградировать на каждом запросе. Границу стережёт
`tests/contract/test_model_runtime_pins.py`, проверяя и манифест, и `uv.lock`.
