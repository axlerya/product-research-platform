"""Реализация ``IndexingJobRepository`` поверх SQLAlchemy."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from indexing_service.domain.entities.indexing_job import IndexingJob
from indexing_service.domain.value_objects.identifiers import JobId, ProductId
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
        self, product_id: ProductId, content_version: int
    ) -> IndexingJob | None:
        stmt = select(IndexingJobORM).where(
            IndexingJobORM.product_id == product_id.value,
            IndexingJobORM.content_version == content_version,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return IndexingJobMapper.to_domain(row) if row is not None else None
