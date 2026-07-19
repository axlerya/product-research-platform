# indexing-service

Построитель поисковой read-model для платформы исследования товаров: потребляет
события об изменениях каталога из RabbitMQ (FastStream), формирует поисковые
документы, считает **dense + sparse** эмбеддинги через **BGE-M3** и поддерживает
коллекцию **Qdrant** в актуальном состоянии. Изменение цены/остатка/метрик
обновляет payload **без пересоздания эмбеддингов**.

> Архитектура и ключевые решения — в [`ARCHITECTURE.md`](./ARCHITECTURE.md).
> Правила разработки (Clean Architecture, TDD, ветки/коммиты) — в
> [`AGENTS.md`](./AGENTS.md).

## Разработка

```bash
# Зависимости (dev-группа + рантайм; тяжёлый эмбеддер — extra "embedding").
uv sync

# Тесты (быстрые, без Qdrant/RabbitMQ)
uv run pytest -m "not integration and not contract"

# Линт + правило зависимостей слоёв
uv run ruff check .
uv run lint-imports
```

## Статус

В разработке. Реализация ведётся по слоям снаружи-внутрь через TDD; первым
поднимается доменный слой (чистый stdlib).
