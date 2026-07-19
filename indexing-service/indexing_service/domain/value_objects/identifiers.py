"""Типобезопасный идентификатор товара ``ProductId`` (uuidv7).

Товаром владеет ``catalog-service``; сюда ``product_id`` приходит в событии
как ``aggregate_id`` и используется id-точки Qdrant. uuidv7 совместим с
требованием Qdrant «id точки — uint64 или UUID-строка».
"""

import os
import time
from dataclasses import dataclass
from typing import Self
from uuid import UUID


def _uuid7() -> UUID:
    """Генерирует ``UUID`` версии 7 (RFC 9562) из времени и энтропии.

    Returns:
        Новый ``UUID`` версии 7, вариант RFC 4122.
    """
    unix_ms = time.time_ns() // 1_000_000
    value = (unix_ms & 0xFFFFFFFFFFFF) << 80
    value |= int.from_bytes(os.urandom(10), "big") & ((1 << 76) - 1)
    value &= ~(0xF << 76)
    value |= 0x7 << 76  # версия 7
    value &= ~(0x3 << 62)
    value |= 0x2 << 62  # вариант RFC 4122
    return UUID(int=value)


@dataclass(frozen=True, slots=True)
class ProductId:
    """Идентификатор товара — обёртка над ``UUID``.

    Attributes:
        value: Значение идентификатора.
    """

    value: UUID

    @classmethod
    def new(cls) -> Self:
        """Создаёт новый идентификатор с uuidv7."""
        return cls(_uuid7())
