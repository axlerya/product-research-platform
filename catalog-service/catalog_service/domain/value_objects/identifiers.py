"""Типобезопасные идентификаторы сущностей (uuidv7).

Разные типы (``ProductId``/``CategoryId``/…) нельзя перепутать: они не
равны даже при одинаковом значении ``UUID``.
"""

import os
import time
from dataclasses import dataclass
from typing import Self
from uuid import UUID


def _uuid7() -> UUID:
    """Генерирует ``UUID`` версии 7 (RFC 9562) из времени и энтропии.

    Временная упорядоченность uuidv7 даёт локальность вставок в B-tree.

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
class _Identifier:
    """Базовый идентификатор — обёртка над ``UUID``.

    Attributes:
        value: Значение идентификатора.
    """

    value: UUID

    @classmethod
    def new(cls) -> Self:
        """Создаёт новый идентификатор с uuidv7."""
        return cls(_uuid7())


@dataclass(frozen=True, slots=True)
class ProductId(_Identifier):
    """Идентификатор товара."""


@dataclass(frozen=True, slots=True)
class CategoryId(_Identifier):
    """Идентификатор категории."""


@dataclass(frozen=True, slots=True)
class BrandId(_Identifier):
    """Идентификатор бренда."""


@dataclass(frozen=True, slots=True)
class SupplierId(_Identifier):
    """Идентификатор поставщика."""
