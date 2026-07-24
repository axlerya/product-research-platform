"""RedisTokenBucket — rate limiter по фиксированному окну (RateLimiterPort)."""

from redis.asyncio import Redis

from research_agent_service.application.dto.answer import RateVerdict

_PREFIX = "ratelimit:"


class RedisTokenBucket:
    """Счётчик с TTL: N обращений за окно на ключ принципала."""

    def __init__(self, *, client: Redis) -> None:
        self._client = client

    async def check(
        self, key: str, *, limit: int, window_s: int
    ) -> RateVerdict:
        """Учитывает обращение и решает, разрешено ли оно."""
        redis_key = f"{_PREFIX}{key}"
        count = await self._client.incr(redis_key)
        if count == 1:
            await self._client.expire(redis_key, window_s)
        if count > limit:
            ttl = await self._client.ttl(redis_key)
            return RateVerdict(allowed=False, retry_after_s=float(max(ttl, 0)))
        return RateVerdict(allowed=True)
