"""Use case ``UpdateMetrics`` (C5) — версия растёт, событий нет."""

from catalog_service.application._translate import to_catalog_error
from catalog_service.application.dto.commands import (
    CommandResult,
    UpdateMetricsCommand,
)
from catalog_service.application.event_mapping import build_messages
from catalog_service.application.exceptions import ProductNotFound
from catalog_service.application.ports.services import Clock, IdGenerator
from catalog_service.application.ports.uow import UnitOfWork
from catalog_service.domain.exceptions import DomainError
from catalog_service.domain.value_objects.identifiers import ProductId
from catalog_service.domain.value_objects.metrics import ProductMetrics
from catalog_service.domain.value_objects.rating import Rating


class UpdateMetrics:
    """Заменяет метрики товара (без публикации события, канон D4)."""

    def __init__(
        self, *, uow: UnitOfWork, clock: Clock, id_gen: IdGenerator
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._id_gen = id_gen

    async def execute(self, cmd: UpdateMetricsCommand) -> CommandResult:
        """Выполняет обновление метрик.

        Raises:
            ProductNotFound: Товар не найден.
            ValidationError: Значения метрик невалидны.
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
            try:
                metrics = ProductMetrics(
                    sales_per_month=cmd.sales_per_month,
                    avg_rating=Rating(cmd.avg_rating),
                    review_count=cmd.review_count,
                )
            except DomainError as exc:
                raise to_catalog_error(exc) from exc

            product.update_metrics(metrics, now=now)
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
