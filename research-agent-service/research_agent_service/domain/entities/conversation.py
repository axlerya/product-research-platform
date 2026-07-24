"""Сущность Conversation — корень диалога."""

from datetime import datetime

from research_agent_service.domain.value_objects.identifiers import (
    ConversationId,
)


class Conversation:
    """Агрегат-корень диалога.

    Хранит счётчик сообщений и метку последнего обновления. Мутирующие
    методы принимают ``now`` явно (детерминизм, без внутренних часов).
    """

    __slots__ = ("created_at", "id", "message_count", "title", "updated_at")

    def __init__(
        self,
        *,
        id: ConversationId,
        created_at: datetime,
        title: str | None = None,
        message_count: int = 0,
        updated_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.title = title
        self.created_at = created_at
        self.updated_at = updated_at if updated_at is not None else created_at
        self.message_count = message_count

    def record_message(self, *, now: datetime) -> None:
        """Учитывает добавление сообщения: счётчик +1 и обновляет метку."""
        self.message_count += 1
        self.updated_at = now
