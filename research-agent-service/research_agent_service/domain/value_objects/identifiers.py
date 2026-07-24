"""Типобезопасные идентификаторы сущностей агента (uuidv7).

Разные типы (ConversationId/MessageId/…) нельзя перепутать: они не равны
даже при одинаковом значении UUID. Временная упорядоченность uuidv7 даёт
локальность вставок в B-tree.
"""

import os
import time
from dataclasses import dataclass
from typing import Self
from uuid import UUID


def _uuid7() -> UUID:
    """Генерирует UUID версии 7 (RFC 9562) из времени и энтропии.

    Returns:
        Новый UUID версии 7, вариант RFC 4122.
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
    """Базовый идентификатор — обёртка над UUID.

    Attributes:
        value: Значение идентификатора.
    """

    value: UUID

    @classmethod
    def new(cls) -> Self:
        """Создаёт новый идентификатор с uuidv7."""
        return cls(_uuid7())


@dataclass(frozen=True, slots=True)
class ConversationId(_Identifier):
    """Идентификатор диалога."""


@dataclass(frozen=True, slots=True)
class MessageId(_Identifier):
    """Идентификатор сообщения."""


@dataclass(frozen=True, slots=True)
class AgentRunId(_Identifier):
    """Идентификатор прогона агента."""


@dataclass(frozen=True, slots=True)
class ToolCallId(_Identifier):
    """Идентификатор вызова инструмента."""


@dataclass(frozen=True, slots=True)
class FeedbackId(_Identifier):
    """Идентификатор обратной связи."""
