"""In-memory фейки портов для unit-тестов прикладного слоя.

``FakeVectorIndex`` хранит точки как payload + признак наличия векторов;
водяной знак восстанавливается из payload (как реальный адаптер читает
его из Qdrant). ``FakeUnitOfWork`` даёт транзакционную границу без БД.
"""

from datetime import UTC, datetime

from indexing_service.application.dto.point import PointRecord, WatermarkEntry
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.job_status import RequestStatus
from indexing_service.domain.value_objects.watermark import IndexingWatermark

_FALLBACK_TIME = datetime(2000, 1, 1, tzinfo=UTC)


def _watermark(payload: dict) -> IndexingWatermark:
    content_hash = payload.get("content_hash")
    indexed_at = payload.get("indexed_at")
    return IndexingWatermark(
        aggregate_version=int(payload["aggregate_version"]),
        model_version=str(payload.get("model_version", "")),
        content_hash=ContentHash(content_hash) if content_hash else None,
        indexed_at=(
            datetime.fromisoformat(indexed_at)
            if isinstance(indexed_at, str)
            else _FALLBACK_TIME
        ),
    )


class FakeVectorIndex:
    """In-memory ``VectorIndex``: точка = payload + признак векторов."""

    def __init__(self) -> None:
        self._points: dict[ProductId, dict] = {}
        self.upserts: list[PointRecord] = []
        self.vector_updates: list[ProductId] = []
        self.payload_sets: list[tuple[ProductId, dict]] = []
        self.payload_upserts: list[tuple[ProductId, dict]] = []

    def preload(self, product_id: ProductId, payload: dict) -> None:
        self._points[product_id] = {"payload": dict(payload), "vectors": True}

    async def get_watermark(
        self, product_id: ProductId
    ) -> IndexingWatermark | None:
        entry = self._points.get(product_id)
        return _watermark(entry["payload"]) if entry else None

    async def scroll_watermarks(self):
        for product_id, entry in self._points.items():
            payload = entry["payload"]
            if "aggregate_version" not in payload:
                continue
            yield WatermarkEntry(
                product_id=product_id,
                watermark=_watermark(payload),
                is_deleted=bool(payload.get("is_deleted", False)),
            )

    async def upsert_document(self, point: PointRecord) -> None:
        self._points[point.product_id] = {
            "payload": dict(point.payload),
            "vectors": True,
        }
        self.upserts.append(point)

    async def upsert_payload(self, product_id, fields) -> None:
        entry = self._points.setdefault(
            product_id, {"payload": {}, "vectors": False}
        )
        entry["payload"].update(fields)
        self.payload_upserts.append((product_id, dict(fields)))

    async def update_vectors(self, product_id, embedding) -> None:
        entry = self._points.setdefault(
            product_id, {"payload": {}, "vectors": False}
        )
        entry["vectors"] = True
        self.vector_updates.append(product_id)

    async def set_payload(self, product_id, fields) -> None:
        entry = self._points.setdefault(
            product_id, {"payload": {}, "vectors": False}
        )
        entry["payload"].update(fields)
        self.payload_sets.append((product_id, dict(fields)))

    def payload_of(self, product_id: ProductId) -> dict:
        return self._points[product_id]["payload"]

    def exists(self, product_id: ProductId) -> bool:
        return product_id in self._points


class FakeVectorIndexAdmin:
    """In-memory ``VectorIndexAdmin`` — общий ``FakeVectorIndex`` writer."""

    def __init__(self) -> None:
        self.index = FakeVectorIndex()
        self.provisioned: list[str] = []
        self.swaps: list[tuple[str, str]] = []

    async def provision(self, collection: str) -> None:
        self.provisioned.append(collection)

    async def swap_alias(self, alias: str, to_collection: str) -> None:
        self.swaps.append((alias, to_collection))

    def writer(self, collection: str) -> FakeVectorIndex:
        return self.index


class FakeCatalogGateway:
    """In-memory ``CatalogGateway``."""

    def __init__(self, snapshots=None) -> None:
        self._by_id = {
            ProductId(snapshot.product_id): snapshot
            for snapshot in (snapshots or [])
        }

    async def get_product(self, product_id: ProductId):
        return self._by_id.get(product_id)

    async def _iter(self):
        for snapshot in self._by_id.values():
            yield snapshot

    def iter_products(self, *, batch: int = 100):
        return self._iter()


class FakeJobRepository:
    """In-memory ``IndexingJobRepository``."""

    def __init__(self) -> None:
        self.store: dict = {}
        self._by_product: dict[tuple, object] = {}

    async def upsert(self, job) -> None:
        self.store[job.job_id] = job
        key = (job.product_id, job.content_version, job.target_collection)
        self._by_product[key] = job

    async def get(self, job_id):
        return self.store.get(job_id)

    async def get_by_product(
        self, product_id, content_version, target_collection=None
    ):
        key = (product_id, content_version, target_collection)
        return self._by_product.get(key)

    async def epoch_counts(self, target_collection):
        counts: dict = {}
        for job in self.store.values():
            if job.target_collection == target_collection:
                counts[job.status] = counts.get(job.status, 0) + 1
        return counts


class FakeRequestRepository:
    """In-memory ``EmbeddingRequestRepository``."""

    def __init__(self) -> None:
        self.store: dict = {}

    async def add(self, request) -> None:
        self.store[request.request_id] = request

    async def get(self, request_id):
        return self.store.get(request_id)

    async def update(self, request) -> None:
        self.store[request.request_id] = request

    async def find_stale(self, older_than, *, limit: int = 100):
        pending = (RequestStatus.PENDING, RequestStatus.AWAITING)
        stale = [
            request
            for request in self.store.values()
            if request.status in pending
            and (request.requested_at or request.created_at) < older_than
        ]
        stale.sort(key=lambda request: request.created_at)
        return stale[:limit]


class FakeOutboxRepository:
    """In-memory ``OutboxRepository``."""

    def __init__(self) -> None:
        self.messages: list = []

    async def add_many(self, messages) -> None:
        self.messages.extend(messages)


class FakeUnitOfWork:
    """In-memory ``UnitOfWork``: три репозитория + счётчик коммитов."""

    def __init__(self) -> None:
        self.jobs = FakeJobRepository()
        self.requests = FakeRequestRepository()
        self.outbox = FakeOutboxRepository()
        self.commits = 0

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


class FixedClock:
    """``Clock`` с фиксированным моментом."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment
