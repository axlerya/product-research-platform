"""Use case ``UpdateCommercialData`` (C3)."""

from catalog_service.application._translate import to_catalog_error
from catalog_service.application.dto.commands import (
    CommandResult,
    UpdateCommercialDataCommand,
)
from catalog_service.application.event_mapping import build_messages
from catalog_service.application.exceptions import ProductNotFound
from catalog_service.application.ports.services import Clock, IdGenerator
from catalog_service.application.ports.uow import UnitOfWork
from catalog_service.domain.entities.product import Product
from catalog_service.domain.exceptions import DomainError
from catalog_service.domain.value_objects.currency import Currency
from catalog_service.domain.value_objects.identifiers import ProductId
from catalog_service.domain.value_objects.money import Money
from catalog_service.domain.value_objects.pricing import Pricing
from catalog_service.domain.value_objects.references import SupplierRef
from catalog_service.domain.value_objects.stock import StockLevel


class UpdateCommercialData:
    """Частично меняет коммерческие данные товара и публикует событие."""

    def __init__(
        self, *, uow: UnitOfWork, clock: Clock, id_gen: IdGenerator
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._id_gen = id_gen

    async def execute(self, cmd: UpdateCommercialDataCommand) -> CommandResult:
        """Выполняет обновление коммерческих данных (диффом).

        Raises:
            ProductNotFound: Товар не найден.
            ValidationError: Значения не прошли доменную валидацию.
            ConcurrencyConflict: Версия в хранилище не совпала.
        """
        now = self._clock.now()
        async with self._uow as uow:
            product = await uow.products.get_by_id(ProductId(cmd.product_id))
            if product is None:
                raise ProductNotFound(
                    f"Товар не найден: {cmd.product_id}",
                    meta={"product_id": str(cmd.product_id)},
                )
            supplier_ref = None
            if cmd.supplier_name is not None:
                supplier = await uow.suppliers.get_or_create(cmd.supplier_name)
                supplier_ref = SupplierRef(supplier.id, supplier.name)
            try:
                pricing = self._build_pricing(cmd, product)
                stock = (
                    StockLevel(cmd.stock_quantity)
                    if cmd.stock_quantity is not None
                    else None
                )
                product.change_commercial(
                    pricing=pricing,
                    stock=stock,
                    supplier=supplier_ref,
                    now=now,
                )
            except DomainError as exc:
                raise to_catalog_error(exc) from exc

            await uow.products.update(
                product, expected_version=cmd.expected_version
            )
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

    @staticmethod
    def _build_pricing(
        cmd: UpdateCommercialDataCommand, product: Product
    ) -> Pricing | None:
        """Собирает новый ``Pricing`` для частичного обновления цены/цены."""
        if cmd.price_amount is None and cmd.cost_amount is None:
            return None
        currency = (
            Currency(cmd.currency)
            if cmd.currency
            else product.pricing.price.currency
        )
        price = (
            Money.of(cmd.price_amount, currency)
            if cmd.price_amount is not None
            else product.pricing.price
        )
        cost = (
            Money.of(cmd.cost_amount, currency)
            if cmd.cost_amount is not None
            else product.pricing.cost
        )
        return Pricing(price=price, cost=cost)
