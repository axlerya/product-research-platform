"""Реализация порта ``IdGenerator`` — временно-упорядоченный uuid7."""

import os
import time
from uuid import UUID


class UuidGenerator:
    """Генератор uuid7 (48 бит времени + случайность; версия 7)."""

    def new_uuid7(self) -> UUID:
        unix_ms = int(time.time() * 1000)
        raw = bytearray(unix_ms.to_bytes(6, "big") + os.urandom(10))
        raw[6] = (raw[6] & 0x0F) | 0x70  # версия 7
        raw[8] = (raw[8] & 0x3F) | 0x80  # вариант RFC 4122
        return UUID(bytes=bytes(raw))
