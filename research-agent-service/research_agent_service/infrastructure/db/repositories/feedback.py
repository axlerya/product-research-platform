"""SQLAlchemy-репозиторий обратной связи."""

from sqlalchemy.ext.asyncio import AsyncSession

from research_agent_service.domain.entities.feedback import Feedback
from research_agent_service.infrastructure.db.mappers import feedback_to_orm


class SqlAlchemyFeedbackRepository:
    """Обратная связь."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, feedback: Feedback) -> None:
        self._session.add(feedback_to_orm(feedback))
