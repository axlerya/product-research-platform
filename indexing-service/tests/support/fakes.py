"""In-memory фейки портов для unit-тестов прикладного слоя.

``FakeVectorIndex`` хранит точки как payload + признак наличия векторов;
водяной знак восстанавливается из payload (как реальный адаптер читает
его из Qdrant). ``FakeUnitOfWork`` даёт транзакционную границу без БД.

Модель точек — chunked: у товара есть корневая точка (``chunk_ix`` 0 или
отсутствует, id == UUID товара) и, после rechunk, дополнительные чанк-точки.
``set_payload`` бьёт по всем точкам товара (как фильтр ``product_id`` в
Qdrant), ``scroll_watermarks`` отдаёт только корневые.
"""

from datetime import UTC, datetime
from uuid import UUID

from indexing_service.application.chunk_identity import chunk_point_id
from indexing_service.application.dto.point import PointRecord, WatermarkEntry
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.job_status import RequestStatus
from indexing_service.domain.value_objects.watermark import IndexingWatermark

_FALLBACK_TIME = datetime(2000, 1, 1, tzinfo=UTC)


def _is_root(payload: dict) -> bool:
    """Корневая точка товара: ``chunk_ix`` отсутствует или равен нулю."""
    return int(payload.get("chunk_ix", 0)) == 0


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
        # Ключ — id точки Qdrant (строка), а не товар: у товара может быть
        # несколько точек (корневая + чанки после rechunk).
        self._points: dict[str, dict] = {}
        self.upserts: list[PointRecord] = []
        self.vector_updates: list[ProductId] = []
        self.payload_sets: list[tuple[ProductId, dict]] = []
        self.payload_upserts: list[tuple[ProductId, dict]] = []

    def preload(self, product_id: ProductId, payload: dict) -> None:
        """Кладёт корневую точку товара."""
        self._write(str(product_id.value), payload, vectors=True)

    def preload_chunk(
        self, product_id: ProductId, chunk_ix: int, payload: dict
    ) -> None:
        """Кладёт чанк-точку товара (``chunk_ix`` > 0) — как пишет sink."""
        point_id = chunk_point_id(product_id.value, chunk_ix)
        self._write(
            point_id,
            {
                **payload,
                "product_id": str(product_id.value),
                "chunk_ix": chunk_ix,
            },
            vectors=True,
        )

    def _write(self, point_id: str, payload: dict, *, vectors: bool) -> None:
        self._points[point_id] = {
            "payload": dict(payload),
            "vectors": vectors,
        }

    def _entry(self, point_id: str) -> dict:
        return self._points.setdefault(
            point_id, {"payload": {}, "vectors": False}
        )

    def _points_of(self, product_id: ProductId) -> list[dict]:
        """Все точки товара: корневая по id + чанки по ``product_id``."""
        root_id = str(product_id.value)
        matched = [
            entry
            for point_id, entry in self._points.items()
            if point_id == root_id
            or entry["payload"].get("product_id") == root_id
        ]
        return matched or [self._entry(root_id)]

    async def get_watermark(
        self, product_id: ProductId
    ) -> IndexingWatermark | None:
        entry = self._points.get(str(product_id.value))
        return _watermark(entry["payload"]) if entry else None

    async def scroll_watermarks(self):
        for point_id, entry in self._points.items():
            payload = entry["payload"]
            if "aggregate_version" not in payload or not _is_root(payload):
                continue
            yield WatermarkEntry(
                product_id=ProductId(UUID(point_id)),
                watermark=_watermark(payload),
                is_deleted=bool(payload.get("is_deleted", False)),
            )

    async def upsert_document(self, point: PointRecord) -> None:
        self._write(str(point.product_id.value), point.payload, vectors=True)
        self.upserts.append(point)

    async def upsert_payload(self, product_id, fields) -> None:
        # Создаёт/обновляет только корневую точку товара.
        self._entry(str(product_id.value))["payload"].update(fields)
        self.payload_upserts.append((product_id, dict(fields)))

    async def update_vectors(self, product_id, embedding) -> None:
        self._entry(str(product_id.value))["vectors"] = True
        self.vector_updates.append(product_id)

    async def set_payload(self, product_id, fields) -> None:
        # Мерж во ВСЕ точки товара (в Qdrant — фильтр по ``product_id``).
        for entry in self._points_of(product_id):
            entry["payload"].update(fields)
        self.payload_sets.append((product_id, dict(fields)))

    def payload_of(self, product_id: ProductId) -> dict:
        """Payload корневой точки товара."""
        return self._points[str(product_id.value)]["payload"]

    def chunk_payloads(self, product_id: ProductId) -> list[dict]:
        """Payload'ы чанк-точек товара (``chunk_ix`` > 0)."""
        root_id = str(product_id.value)
        return [
            entry["payload"]
            for entry in self._points.values()
            if entry["payload"].get("product_id") == root_id
            and not _is_root(entry["payload"])
        ]

    def exists(self, product_id: ProductId) -> bool:
        return str(product_id.value) in self._points


class FakeVectorIndexAdmin:
    """In-memory ``VectorIndexAdmin``: свой ``FakeVectorIndex`` на коллекцию."""

    def __init__(self, *, alias: str = "products") -> None:
        self.index = FakeVectorIndex()
        self._writers: dict[str, FakeVectorIndex] = {alias: self.index}
        self.provisioned: list[str] = []
        self.swaps: list[tuple[str, str]] = []
        # Сколько готовых корневых точек эпохи «лежит» в коллекции.
        self.ready_roots: dict[str, int] = {}

    async def provision(self, collection: str) -> None:
        self.provisioned.append(collection)

    async def swap_alias(self, alias: str, to_collection: str) -> None:
        self.swaps.append((alias, to_collection))

    def writer(self, collection: str) -> FakeVectorIndex:
        return self._writers.setdefault(collection, FakeVectorIndex())

    async def count_ready_roots(
        self,
        collection: str,
        *,
        epoch: str,
        expected_model: str | None = None,
    ) -> int:
        return self.ready_roots.get(collection, 0)


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
