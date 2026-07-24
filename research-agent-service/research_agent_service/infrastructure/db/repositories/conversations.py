"""SQLAlchemy-репозиторий диалогов и сообщений."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from research_agent_service.domain.entities.conversation import Conversation
from research_agent_service.domain.entities.message import Message
from research_agent_service.domain.value_objects.identifiers import (
    ConversationId,
    MessageId,
)
from research_agent_service.infrastructure.db.mappers import (
    conversation_from_orm,
    conversation_to_orm,
    message_from_orm,
    message_to_orm,
)
from research_agent_service.infrastructure.db.models import (
    ConversationORM,
    MessageORM,
)


class SqlAlchemyConversationRepository:
    """Диалоги и их сообщения на одной сессии."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, conversation: Conversation) -> None:
        self._session.add(conversation_to_orm(conversation))

    async def get(self, conversation_id: ConversationId) -> Conversation | None:
        orm = await self._session.get(ConversationORM, conversation_id.value)
        return conversation_from_orm(orm) if orm is not None else None

    async def add_message(self, message: Message) -> None:
        self._session.add(message_to_orm(message))

    async def get_message(self, message_id: MessageId) -> Message | None:
        orm = await self._session.get(MessageORM, message_id.value)
        return message_from_orm(orm) if orm is not None else None

    async def load_history(
        self, conversation_id: ConversationId, *, limit: int
    ) -> tuple[Message, ...]:
        stmt = (
            select(MessageORM)
            .where(MessageORM.conversation_id == conversation_id.value)
            .order_by(MessageORM.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return tuple(message_from_orm(row) for row in reversed(rows))
