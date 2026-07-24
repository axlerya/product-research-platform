"""Uuid7Generator — генератор uuidv7 (реализация порта IdGenerator)."""

import os
import time
from uuid import UUID


class Uuid7Generator:
    """Источник uuidv7 (RFC 9562) из времени и энтропии."""

    def new_uuid7(self) -> UUID:
        """Возвращает новый UUID версии 7, вариант RFC 4122."""
        unix_ms = time.time_ns() // 1_000_000
        value = (unix_ms & 0xFFFFFFFFFFFF) << 80
        value |= int.from_bytes(os.urandom(10), "big") & ((1 << 76) - 1)
        value &= ~(0xF << 76)
        value |= 0x7 << 76  # версия 7
        value &= ~(0x3 << 62)
        value |= 0x2 << 62  # вариант RFC 4122
        return UUID(int=value)
