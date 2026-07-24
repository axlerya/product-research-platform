"""Тесты Redis-адаптеров на фейковом клиенте."""

from research_agent_service.infrastructure.redis.cache import RedisCache
from research_agent_service.infrastructure.redis.rate_limiter import (
    RedisTokenBucket,
)


class _FakeRedis:
    """Мини-Redis в памяти (decode_responses=True семантика)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.counters: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, *, ex: int | None = None) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)

    async def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.expires[key] = seconds

    async def ttl(self, key: str) -> int:
        return self.expires.get(key, -1)


async def test_cache_set_get_delete() -> None:
    """Кеш кладёт, отдаёт и удаляет значение."""
    cache = RedisCache(client=_FakeRedis())  # type: ignore[arg-type]

    await cache.set("k", "v", ttl_s=60)
    assert await cache.get("k") == "v"

    await cache.delete("k")
    assert await cache.get("k") is None


async def test_cache_missing_returns_none() -> None:
    """Отсутствующий ключ → None."""
    cache = RedisCache(client=_FakeRedis())  # type: ignore[arg-type]

    assert await cache.get("absent") is None


async def test_rate_limiter_allows_within_limit() -> None:
    """В пределах лимита обращения разрешены; на первом ставится TTL."""
    fake = _FakeRedis()
    limiter = RedisTokenBucket(client=fake)  # type: ignore[arg-type]

    first = await limiter.check("c1", limit=2, window_s=30)
    second = await limiter.check("c1", limit=2, window_s=30)

    assert first.allowed
    assert second.allowed
    assert fake.expires["ratelimit:c1"] == 30


async def test_rate_limiter_blocks_over_limit() -> None:
    """Сверх лимита — отказ с retry_after из TTL."""
    limiter = RedisTokenBucket(client=_FakeRedis())  # type: ignore[arg-type]

    await limiter.check("c1", limit=1, window_s=30)
    verdict = await limiter.check("c1", limit=1, window_s=30)

    assert not verdict.allowed
    assert verdict.retry_after_s == 30.0
