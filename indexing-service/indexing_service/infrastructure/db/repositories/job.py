"""Реализация ``IndexingJobRepository`` поверх SQLAlchemy."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from indexing_service.domain.entities.indexing_job import IndexingJob
from indexing_service.domain.value_objects.identifiers import JobId, ProductId
from indexing_service.domain.value_objects.job_status import JobStatus
from indexing_service.infrastructure.db.mappers import IndexingJobMapper
from indexing_service.infrastructure.db.models import IndexingJobORM


class SqlAlchemyIndexingJobRepository:
    """Хранилище агрегата ``IndexingJob`` (upsert по ``job_id``)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, job: IndexingJob) -> None:
        """Идемпотентно сохраняет job (INSERT либо UPDATE по PK)."""
        await self._session.merge(IndexingJobMapper.to_orm(job))
        await self._session.flush()

    async def get(self, job_id: JobId) -> IndexingJob | None:
        row = await self._session.get(IndexingJobORM, job_id.value)
        return IndexingJobMapper.to_domain(row) if row is not None else None

    async def get_by_product(
        self,
        product_id: ProductId,
        content_version: int,
        target_collection: str | None = None,
    ) -> IndexingJob | None:
        stmt = select(IndexingJobORM).where(
            IndexingJobORM.product_id == product_id.value,
            IndexingJobORM.content_version == content_version,
            # NULL = «пишем в alias»; сравниваем как индекс (COALESCE).
            func.coalesce(IndexingJobORM.target_collection, "")
            == (target_collection or ""),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return IndexingJobMapper.to_domain(row) if row is not None else None

    async def epoch_counts(
        self, target_collection: str
    ) -> dict[JobStatus, int]:
        """Считает задания коллекции по статусам (прогресс reindex, Q6)."""
        stmt = (
            select(IndexingJobORM.status, func.count())
            .where(IndexingJobORM.target_collection == target_collection)
            .group_by(IndexingJobORM.status)
        )
        rows = (await self._session.execute(stmt)).all()
        return {JobStatus(status): count for status, count in rows}
