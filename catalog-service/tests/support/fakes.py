"""In-memory фейки портов для unit-тестов прикладного слоя.

Фейк репозитория товара клонирует агрегат при чтении (``reconstitute``),
чтобы мутации use case не затрагивали «хранимую» копию — это корректно
эмулирует оптимистичную блокировку по версии, как реальная БД.
"""

from datetime import UTC, datetime
from uuid import UUID

from catalog_service.application.exceptions import ConcurrencyConflict
from catalog_service.application.outbox_message import OutboxMessage
from catalog_service.domain.entities.product import Product
from catalog_service.domain.entities.reference import (
    Brand,
    Category,
    Supplier,
)
from catalog_service.domain.value_objects.identifiers import (
    BrandId,
    CategoryId,
    ProductId,
    SupplierId,
)
from catalog_service.domain.value_objects.sku import Sku

_REF_NOW = datetime(2026, 7, 18, 10, 15, 30, tzinfo=UTC)


def _clone(product: Product) -> Product:
    """Возвращает свежую копию агрегата (эмуляция чтения из БД)."""
    return Product.reconstitute(
        id=product.id,
        sku=product.sku,
        name=product.name,
        description=product.description,
        category=product.category,
        brand=product.brand,
        supplier=product.supplier,
        pricing=product.pricing,
        stock=product.stock,
        metrics=product.metrics,
        source_updated_at=product.source_updated_at,
        version=product.version,
        is_deleted=product.is_deleted,
        created_at=product.created_at,
        updated_at=product.updated_at,
        deleted_at=product.deleted_at,
    )


class FakeProductRepository:
    """In-memory реализация ``ProductRepository``."""

    def __init__(self) -> None:
        self._by_id: dict[ProductId, Product] = {}
        self._by_sku: dict[Sku, ProductId] = {}

    def preload(self, product: Product) -> None:
        """Кладёт товар в хранилище напрямую (для сценариев обновления)."""
        self._by_id[product.id] = _clone(product)
        self._by_sku[product.sku] = product.id

    async def get_by_id(self, product_id: ProductId) -> Product | None:
        stored = self._by_id.get(product_id)
        return _clone(stored) if stored is not None else None

    async def get_by_sku(self, sku: Sku) -> Product | None:
        pid = self._by_sku.get(sku)
        stored = self._by_id.get(pid) if pid is not None else None
        return _clone(stored) if stored is not None else None

    async def add(self, product: Product) -> None:
        self._by_id[product.id] = _clone(product)
        self._by_sku[product.sku] = product.id

    async def update(self, product: Product, *, expected_version: int) -> None:
        stored = self._by_id.get(product.id)
        if stored is None or stored.version != expected_version:
            raise ConcurrencyConflict(
                f"Товар {product.sku.value} изменён параллельно",
                meta={
                    "sku": product.sku.value,
                    "expected_version": expected_version,
                },
            )
        self._by_id[product.id] = _clone(product)


class _FakeReferenceRepo:
    """Общая база фейковых справочников (get-or-create по имени)."""

    def __init__(self, entity_cls, id_cls) -> None:
        self._entity_cls = entity_cls
        self._id_cls = id_cls
        self._by_name: dict[str, object] = {}

    async def get_or_create(self, name: str):
        name = name.strip()
        if name not in self._by_name:
            self._by_name[name] = self._entity_cls(
                id=self._id_cls.new(), name=name, created_at=_REF_NOW
            )
        return self._by_name[name]


class FakeCategoryRepository(_FakeReferenceRepo):
    """In-memory ``CategoryRepository``."""

    def __init__(self) -> None:
        super().__init__(Category, CategoryId)


class FakeBrandRepository(_FakeReferenceRepo):
    """In-memory ``BrandRepository``."""

    def __init__(self) -> None:
        super().__init__(Brand, BrandId)


class FakeSupplierRepository(_FakeReferenceRepo):
    """In-memory ``SupplierRepository``."""

    def __init__(self) -> None:
        super().__init__(Supplier, SupplierId)


class FakeOutbox:
    """In-memory ``OutboxRepository`` — копит сообщения в список."""

    def __init__(self) -> None:
        self.messages: list[OutboxMessage] = []

    async def add_many(self, messages) -> None:
        self.messages.extend(messages)


class FakeUnitOfWork:
    """In-memory ``UnitOfWork`` с флагами commit/rollback."""

    def __init__(self) -> None:
        self.products = FakeProductRepository()
        self.categories = FakeCategoryRepository()
        self.brands = FakeBrandRepository()
        self.suppliers = FakeSupplierRepository()
        self.outbox = FakeOutbox()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FixedClock:
    """``Clock``-порт: всегда возвращает фиксированный момент."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


class SequenceIdGenerator:
    """``IdGenerator``-порт с предзаданными id (иначе — генерация)."""

    def __init__(self, product_ids=None, message_ids=None) -> None:
        self._product_ids = list(product_ids or [])
        self._message_ids = list(message_ids or [])
        self._message_counter = 0

    def new_product_id(self) -> ProductId:
        if self._product_ids:
            return self._product_ids.pop(0)
        return ProductId.new()

    def new_message_id(self) -> UUID:
        if self._message_ids:
            return self._message_ids.pop(0)
        self._message_counter += 1
        return UUID(int=self._message_counter)
