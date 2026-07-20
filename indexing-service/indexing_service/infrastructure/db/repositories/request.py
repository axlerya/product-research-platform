"""Реализация ``EmbeddingRequestRepository`` поверх SQLAlchemy."""

from sqlalchemy.ext.asyncio import AsyncSession

from indexing_service.domain.entities.embedding_request import EmbeddingRequest
from indexing_service.domain.value_objects.identifiers import RequestId
from indexing_service.infrastructure.db.mappers import EmbeddingRequestMapper
from indexing_service.infrastructure.db.models import EmbeddingRequestORM


class SqlAlchemyEmbeddingRequestRepository:
    """Хранилище команд ``EmbeddingRequest`` (дочерних к job)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, request: EmbeddingRequest) -> None:
        self._session.add(EmbeddingRequestMapper.to_orm(request))
        await self._session.flush()

    async def get(self, request_id: RequestId) -> EmbeddingRequest | None:
        row = await self._session.get(EmbeddingRequestORM, request_id.value)
        if row is None:
            return None
        return EmbeddingRequestMapper.to_domain(row)

    async def update(self, request: EmbeddingRequest) -> None:
        """Обновляет статус/времена команды (UPDATE по PK)."""
        await self._session.merge(EmbeddingRequestMapper.to_orm(request))
        await self._session.flush()
