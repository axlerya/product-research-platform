"""Агрегат ``Product`` — корень товарного агрегата.

Единственный источник классификации «поле → событие». Мутаторы
идемпотентны: при отсутствии фактического изменения не меняют версию и
не порождают событий. За одну команду версия растёт не более чем на 1.
"""

from datetime import date, datetime

from catalog_service.domain.events import (
    DomainEvent,
    ProductCommercialDataChanged,
    ProductContentChanged,
    ProductCreated,
    ProductDeleted,
)
from catalog_service.domain.value_objects.identifiers import ProductId
from catalog_service.domain.value_objects.margin import Margin
from catalog_service.domain.value_objects.metrics import ProductMetrics
from catalog_service.domain.value_objects.pricing import Pricing
from catalog_service.domain.value_objects.references import (
    BrandRef,
    CategoryRef,
    SupplierRef,
)
from catalog_service.domain.value_objects.sku import Sku
from catalog_service.domain.value_objects.stock import StockLevel


class Product:
    """Агрегат-корень товара.

    Инкапсулирует контент, коммерческие данные, остаток и метрики.
    Оптимистичная блокировка — через поле ``version``. Мутирующие методы
    принимают ``now`` явно (детерминизм).
    """

    __slots__ = (
        "_events",
        "_version_bumped",
        "brand",
        "category",
        "created_at",
        "deleted_at",
        "description",
        "id",
        "is_deleted",
        "metrics",
        "name",
        "pricing",
        "sku",
        "source_updated_at",
        "stock",
        "supplier",
        "updated_at",
        "version",
    )

    def __init__(
        self,
        *,
        id: ProductId,
        sku: Sku,
        name: str,
        description: str,
        category: CategoryRef,
        brand: BrandRef,
        supplier: SupplierRef,
        pricing: Pricing,
        stock: StockLevel,
        metrics: ProductMetrics,
        source_updated_at: date | None,
        version: int,
        is_deleted: bool,
        created_at: datetime,
        updated_at: datetime,
        deleted_at: datetime | None,
    ) -> None:
        self.id = id
        self.sku = sku
        self.name = name
        self.description = description
        self.category = category
        self.brand = brand
        self.supplier = supplier
        self.pricing = pricing
        self.stock = stock
        self.metrics = metrics
        self.source_updated_at = source_updated_at
        self.version = version
        self.is_deleted = is_deleted
        self.created_at = created_at
        self.updated_at = updated_at
        self.deleted_at = deleted_at
        self._events: list[DomainEvent] = []
        self._version_bumped = False

    @classmethod
    def create(
        cls,
        *,
        id: ProductId,
        sku: Sku,
        name: str,
        description: str,
        category: CategoryRef,
        brand: BrandRef,
        supplier: SupplierRef,
        pricing: Pricing,
        stock: StockLevel,
        metrics: ProductMetrics,
        source_updated_at: date | None,
        now: datetime,
    ) -> "Product":
        """Создаёт товар и накапливает событие ``ProductCreated``."""
        product = cls(
            id=id,
            sku=sku,
            name=name,
            description=description,
            category=category,
            brand=brand,
            supplier=supplier,
            pricing=pricing,
            stock=stock,
            metrics=metrics,
            source_updated_at=source_updated_at,
            version=1,
            is_deleted=False,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        product._events.append(ProductCreated(product_id=id, occurred_at=now))
        product._version_bumped = True
        return product

    @classmethod
    def reconstitute(
        cls,
        *,
        id: ProductId,
        sku: Sku,
        name: str,
        description: str,
        category: CategoryRef,
        brand: BrandRef,
        supplier: SupplierRef,
        pricing: Pricing,
        stock: StockLevel,
        metrics: ProductMetrics,
        source_updated_at: date | None,
        version: int,
        is_deleted: bool,
        created_at: datetime,
        updated_at: datetime,
        deleted_at: datetime | None,
    ) -> "Product":
        """Восстанавливает товар из хранилища без эмиссии события."""
        return cls(
            id=id,
            sku=sku,
            name=name,
            description=description,
            category=category,
            brand=brand,
            supplier=supplier,
            pricing=pricing,
            stock=stock,
            metrics=metrics,
            source_updated_at=source_updated_at,
            version=version,
            is_deleted=is_deleted,
            created_at=created_at,
            updated_at=updated_at,
            deleted_at=deleted_at,
        )

    def change_content(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        category: CategoryRef | None = None,
        brand: BrandRef | None = None,
        now: datetime,
    ) -> None:
        """Меняет контентные поля; эмитит ``ProductContentChanged``.

        Значение, равное текущему, изменением не считается. Если ничего
        не изменилось — no-op (версия и события не трогаются).

        Args:
            name: Новое название или ``None`` (не менять).
            description: Новое описание или ``None``.
            category: Новая категория или ``None``.
            brand: Новый бренд или ``None``.
            now: Момент операции.
        """
        changed: list[str] = []
        if name is not None and name != self.name:
            self.name = name
            changed.append("name")
        if description is not None and description != self.description:
            self.description = description
            changed.append("description")
        if category is not None and category != self.category:
            self.category = category
            changed.append("category")
        if brand is not None and brand != self.brand:
            self.brand = brand
            changed.append("brand")
        if not changed:
            return
        self._bump_version_once()
        self.updated_at = now
        self._events.append(
            ProductContentChanged(
                product_id=self.id,
                changed_fields=tuple(changed),
                occurred_at=now,
            )
        )

    def change_commercial(
        self,
        *,
        pricing: Pricing | None = None,
        stock: StockLevel | None = None,
        supplier: SupplierRef | None = None,
        now: datetime,
    ) -> None:
        """Меняет коммерческие поля; эмитит ``ProductCommercialDataChanged``.

        ``changed_fields`` перечисляет реально изменившиеся поля в порядке
        price, cost, stock, supplier. Пустой diff — no-op.

        Args:
            pricing: Новая пара цена/себестоимость или ``None``.
            stock: Новый остаток или ``None``.
            supplier: Новый поставщик или ``None``.
            now: Момент операции.
        """
        changed: list[str] = []
        if pricing is not None:
            if pricing.price != self.pricing.price:
                changed.append("price")
            if pricing.cost != self.pricing.cost:
                changed.append("cost")
            if pricing != self.pricing:
                self.pricing = pricing
        if stock is not None and stock != self.stock:
            self.stock = stock
            changed.append("stock")
        if supplier is not None and supplier != self.supplier:
            self.supplier = supplier
            changed.append("supplier")
        if not changed:
            return
        self._bump_version_once()
        self.updated_at = now
        self._events.append(
            ProductCommercialDataChanged(
                product_id=self.id,
                changed_fields=tuple(changed),
                occurred_at=now,
            )
        )

    def update_metrics(self, metrics: ProductMetrics, *, now: datetime) -> None:
        """Обновляет метрики: бампает версию, но НЕ эмитит событие.

        No-op, если новые метрики равны текущим.

        Args:
            metrics: Новые метрики.
            now: Момент операции.
        """
        if metrics == self.metrics:
            return
        self.metrics = metrics
        self._bump_version_once()
        self.updated_at = now

    def delete(self, *, now: datetime) -> None:
        """Мягко удаляет товар; эмитит ``ProductDeleted``. Идемпотентно.

        Args:
            now: Момент операции.
        """
        if self.is_deleted:
            return
        self.is_deleted = True
        self.deleted_at = now
        self._bump_version_once()
        self.updated_at = now
        self._events.append(ProductDeleted(product_id=self.id, occurred_at=now))

    def margin(self) -> Margin:
        """Возвращает маржу товара (делегирует в ``Pricing``)."""
        return self.pricing.calculate_margin()

    def collect_events(self) -> list[DomainEvent]:
        """Возвращает накопленные события и завершает цикл команды.

        Returns:
            Список накопленных доменных событий (может быть пустым).
        """
        events = self._events
        self._events = []
        self._version_bumped = False
        return events

    def _bump_version_once(self) -> None:
        """Увеличивает версию не более одного раза за команду."""
        if not self._version_bumped:
            self.version += 1
            self._version_bumped = True
