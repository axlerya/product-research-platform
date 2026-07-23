"""Реализация ``EmbeddingRequestRepository`` поверх SQLAlchemy."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from indexing_service.domain.entities.embedding_request import EmbeddingRequest
from indexing_service.domain.value_objects.identifiers import RequestId
from indexing_service.domain.value_objects.job_status import (
    JobStatus,
    RequestStatus,
)
from indexing_service.infrastructure.db.mappers import EmbeddingRequestMapper
from indexing_service.infrastructure.db.models import (
    EmbeddingRequestORM,
    IndexingJobORM,
)


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

    async def find_stale(
        self, older_than: datetime, *, limit: int = 100
    ) -> list[EmbeddingRequest]:
        """Команды без ответа дольше таймаута (§10).

        Берём только те, чьё задание ещё не терминально: по завершённой job
        ответ уже не нужен, даже если команда осталась висеть.
        """
        stmt = (
            select(EmbeddingRequestORM)
            .join(
                IndexingJobORM,
                IndexingJobORM.job_id == EmbeddingRequestORM.job_id,
            )
            .where(
                EmbeddingRequestORM.status.in_(
                    (RequestStatus.PENDING, RequestStatus.AWAITING)
                ),
                IndexingJobORM.status.not_in(
                    (JobStatus.DONE, JobStatus.FAILED)
                ),
                func.coalesce(
                    EmbeddingRequestORM.requested_at,
                    EmbeddingRequestORM.created_at,
                )
                < older_than,
            )
            .order_by(EmbeddingRequestORM.created_at)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [EmbeddingRequestMapper.to_domain(row) for row in rows]
