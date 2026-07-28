"""Фабрика клиента Redis для адаптеров кеша и rate limiter.

``decode_responses=True`` здесь не деталь вкуса, а часть контракта: порт
``CachePort`` объявлен в ``str``. Клиент без декодирования отдаёт ``bytes``,
и реплей по idempotency-ключу падает на разборе идентификатора прогона —
повтор запроса возвращает 500 вместо прежнего ответа.
"""

from redis.asyncio import Redis, from_url


def build_redis(url: str) -> Redis:
    """Создаёт клиент Redis, отдающий строки, а не байты."""
    return from_url(url, decode_responses=True)
