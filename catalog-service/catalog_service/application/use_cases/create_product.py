"""Use case ``CreateProduct`` (C1)."""

from catalog_service.application._translate import to_catalog_error
from catalog_service.application.dto.commands import (
    CommandResult,
    CreateProductCommand,
)
from catalog_service.application.event_mapping import build_messages
from catalog_service.application.exceptions import DuplicateSku
from catalog_service.application.ports.services import Clock, IdGenerator
from catalog_service.application.ports.uow import UnitOfWork
from catalog_service.domain.entities.product import Product
from catalog_service.domain.exceptions import DomainError
from catalog_service.domain.value_objects.currency import Currency
from catalog_service.domain.value_objects.metrics import ProductMetrics
from catalog_service.domain.value_objects.money import Money
from catalog_service.domain.value_objects.pricing import Pricing
from catalog_service.domain.value_objects.rating import Rating
from catalog_service.domain.value_objects.references import (
    BrandRef,
    CategoryRef,
    SupplierRef,
)
from catalog_service.domain.value_objects.sku import Sku
from catalog_service.domain.value_objects.stock import StockLevel


class CreateProduct:
    """Создаёт новый товар и публикует событие создания."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: Clock,
        id_gen: IdGenerator,
        default_currency: str,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._id_gen = id_gen
        self._default_currency = default_currency

    async def execute(self, cmd: CreateProductCommand) -> CommandResult:
        """Выполняет создание товара.

        Raises:
            ValidationError: Значения не прошли доменную валидацию.
            DuplicateSku: Товар с таким артикулом уже существует.
        """
        now = self._clock.now()
        try:
            sku = Sku(cmd.sku)
            currency = Currency(cmd.currency or self._default_currency)
            pricing = Pricing(
                price=Money.of(cmd.price_amount, currency),
                cost=Money.of(cmd.cost_amount, currency),
            )
            stock = StockLevel(cmd.stock_quantity)
            metrics = ProductMetrics(
                sales_per_month=cmd.sales_per_month,
                avg_rating=Rating(cmd.avg_rating),
                review_count=cmd.review_count,
            )
        except DomainError as exc:
            raise to_catalog_error(exc) from exc

        async with self._uow as uow:
            if await uow.products.get_by_sku(sku) is not None:
                raise DuplicateSku(
                    f"Товар с артикулом {sku.value} уже существует",
                    meta={"sku": sku.value},
                )
            category = await uow.categories.get_or_create(cmd.category_name)
            brand = await uow.brands.get_or_create(cmd.brand_name)
            supplier = await uow.suppliers.get_or_create(cmd.supplier_name)
            product = Product.create(
                id=self._id_gen.new_product_id(),
                sku=sku,
                name=cmd.name,
                description=cmd.description,
                category=CategoryRef(category.id, category.name),
                brand=BrandRef(brand.id, brand.name),
                supplier=SupplierRef(supplier.id, supplier.name),
                pricing=pricing,
                stock=stock,
                metrics=metrics,
                source_updated_at=cmd.source_updated_at,
                now=now,
            )
            await uow.products.add(product)
            events = product.collect_events()
            await uow.outbox.add_many(
                build_messages(events, product, self._id_gen)
            )
            await uow.commit()

        return CommandResult(
            product_id=product.id.value,
            sku=product.sku.value,
            version=product.version,
            emitted_events=tuple(e.routing_key for e in events),
        )
