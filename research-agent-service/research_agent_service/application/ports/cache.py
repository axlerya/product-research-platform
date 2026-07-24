"""Порт CachePort — кеш и краткоживущее состояние (Redis)."""

from typing import Protocol


class CachePort(Protocol):
    """Строковый кеш с TTL."""

    async def get(self, key: str) -> str | None:
        """Возвращает значение по ключу (или None)."""
        ...

    async def set(self, key: str, value: str, *, ttl_s: int) -> None:
        """Кладёт значение с временем жизни в секундах."""
        ...

    async def delete(self, key: str) -> None:
        """Удаляет ключ."""
        ...
