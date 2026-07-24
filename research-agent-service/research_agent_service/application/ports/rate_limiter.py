"""Порт RateLimiterPort — ограничение частоты по принципалу (Redis)."""

from typing import Protocol

from research_agent_service.application.dto.answer import RateVerdict


class RateLimiterPort(Protocol):
    """Ограничитель частоты запросов."""

    async def check(
        self, key: str, *, limit: int, window_s: int
    ) -> RateVerdict:
        """Проверяет и учитывает обращение по ключу принципала."""
        ...
