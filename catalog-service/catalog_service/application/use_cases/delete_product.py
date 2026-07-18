"""Use case ``DeleteProduct`` (C6) — soft-delete, идемпотентно."""

from catalog_service.application.dto.commands import (
    CommandResult,
    DeleteProductCommand,
)
from catalog_service.application.event_mapping import build_messages
from catalog_service.application.exceptions import ProductNotFound
from catalog_service.application.ports.services import Clock, IdGenerator
from catalog_service.application.ports.uow import UnitOfWork
from catalog_service.domain.value_objects.identifiers import ProductId


class DeleteProduct:
    """Мягко удаляет товар и публикует событие удаления."""

    def __init__(
        self, *, uow: UnitOfWork, clock: Clock, id_gen: IdGenerator
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._id_gen = id_gen

    async def execute(self, cmd: DeleteProductCommand) -> CommandResult:
        """Выполняет мягкое удаление (идемпотентно).

        Raises:
            ProductNotFound: Товар не найден.
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
            product.delete(now=now)
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
