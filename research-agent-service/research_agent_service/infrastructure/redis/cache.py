"""RedisCache — строковый кеш с TTL (реализация порта CachePort)."""

from redis.asyncio import Redis


class RedisCache:
    """Кеш поверх Redis. Клиент создаётся с decode_responses=True."""

    def __init__(self, *, client: Redis) -> None:
        self._client = client

    async def get(self, key: str) -> str | None:
        """Возвращает значение по ключу (или None)."""
        return await self._client.get(key)

    async def set(self, key: str, value: str, *, ttl_s: int) -> None:
        """Кладёт значение с временем жизни в секундах."""
        await self._client.set(key, value, ex=ttl_s)

    async def delete(self, key: str) -> None:
        """Удаляет ключ."""
        await self._client.delete(key)
