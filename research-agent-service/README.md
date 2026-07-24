# research-agent-service

Агент-исследователь товаров для платформы исследования e-commerce. Принимает
пользовательский запрос через REST (FastAPI), **самостоятельно выбирает
инструменты** с помощью LLM и LangGraph, синхронно достаёт данные из внутренних
сервисов и внешнего веб-поиска, формирует **структурированный ответ с
источниками** и надёжно публикует факты о своей работе в RabbitMQ по паттерну
Transactional Outbox.

> Архитектура и ключевые решения — в [`ARCHITECTURE.md`](./ARCHITECTURE.md).
> Правила разработки (Clean Architecture, TDD, ветки/коммиты) — в
> [`AGENTS.md`](./AGENTS.md).

## Границы

Сервис — **оркестратор, а не источник истины**. Актуальные товары и вся ценовая
математика приходят из `catalog-service`, векторное представление запроса — из
`embedding-service`, кандидаты — из read-only Qdrant, внешние факты — из
веб-поиска. Собственная БД хранит только историю диалогов, прогоны агента,
вызовы инструментов, обратную связь и outbox.

- Синхронный `POST /query` **не зависит** от RabbitMQ.
- LLM **не** считает маржу, не выполняет SQL и не ходит в БД.
- Сервис **не пишет** в Qdrant и **не читает** чужие БД.

## Структура (Clean Architecture)

```
research_agent_service/
  domain/          # сущности, value objects, политики, события (только stdlib)
  application/     # use cases, порты (Protocol), DTO
  infrastructure/  # адаптеры: LangGraph, LLM, gRPC, Qdrant, web, Redis, БД, брокер
  presentation/    # FastAPI, FastStream relay, CLI
```

Правило зависимостей — исполняемый инвариант (`ruff` banned-api + `import-linter`):
домен и application не знают фреймворков.

## Разработка

```bash
uv sync                 # виртуальное окружение и зависимости
uv run pytest           # тесты
uv run ruff check .     # линт
uv run ruff format .    # формат
uv run lint-imports     # правило зависимостей Clean Architecture
```

Любой код пишется через TDD (см. `AGENTS.md`). Одна фича — одна ветка и один PR.
