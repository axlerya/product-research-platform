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
