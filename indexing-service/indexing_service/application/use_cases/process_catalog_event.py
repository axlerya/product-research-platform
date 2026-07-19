"""Use case ``ProcessCatalogEvent`` — оркестратор консюмера (U1).

Читает водяной знак, классифицирует изменение (§6.2) и исполняет нужное
действие над Qdrant. Доменные ошибки (poison) переводит в
``EventValidationError`` (→ DLQ); временные ошибки портов пробрасывает.
"""

from indexing_service.application.dto.events import (
    CatalogEvent,
    CommercialChangedEvent,
    ContentChangedEvent,
    ProductCreatedEvent,
    ProductDeletedEvent,
)
from indexing_service.application.dto.snapshot import ProductSnapshot
from indexing_service.application.exceptions import (
    EventValidationError,
    ProductNotInCatalog,
)
from indexing_service.application.indexer import index_snapshot, tombstone
from indexing_service.application.payload import (
    commercial_payload,
    content_payload,
)
from indexing_service.application.ports.catalog_gateway import CatalogGateway
from indexing_service.application.ports.clock import Clock
from indexing_service.application.ports.embedding_model import EmbeddingModel
from indexing_service.application.ports.vector_index import VectorIndex
from indexing_service.domain.exceptions import DomainError
from indexing_service.domain.services.change_classifier import (
    IndexingAction,
    classify,
)
from indexing_service.domain.services.document_composer import compose
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.currency import Currency
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.money import Money
from indexing_service.domain.value_objects.pricing import Pricing
from indexing_service.domain.value_objects.stock import StockLevel


class ProcessCatalogEvent:
    """Обрабатывает одно событие каталога идемпотентно (§6)."""

    def __init__(
        self,
        *,
        index: VectorIndex,
        embedder: EmbeddingModel,
        catalog: CatalogGateway,
        clock: Clock,
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._catalog = catalog
        self._clock = clock

    async def handle(self, event: CatalogEvent) -> IndexingAction:
        """Классифицирует и применяет событие; возвращает действие.

        Raises:
            EventValidationError: Событие нарушает доменные инварианты.
            TransientError: Временный сбой порта (Qdrant/эмбеддер/catalog).
        """
        product_id = ProductId(event.product_id)
        watermark = await self._index.get_watermark(product_id)
        try:
            content_hash = self._content_hash_of(event)
            action = classify(
                event.kind,
                event.aggregate_version,
                watermark,
                content_hash=content_hash,
                current_model=self._embedder.model_id.key,
            )
            await self._apply(action, event, product_id)
            return action
        except DomainError as exc:
            raise EventValidationError(str(exc)) from exc

    @staticmethod
    def _content_hash_of(event: CatalogEvent) -> ContentHash | None:
        """Хэш нового текста — только для content-события (дедуп)."""
        if isinstance(event, ContentChangedEvent):
            text = compose(
                name=event.name,
                brand=event.brand,
                category=event.category,
                description=event.description,
            )
            return ContentHash.of(text.value)
        return None

    async def _apply(
        self,
        action: IndexingAction,
        event: CatalogEvent,
        product_id: ProductId,
    ) -> None:
        if action is IndexingAction.SKIP:
            return
        if action is IndexingAction.FULL_INDEX:
            assert isinstance(event, ProductCreatedEvent)
            await self._full_index(event.product)
        elif action is IndexingAction.REPAIR:
            await self._repair(product_id)
        elif action is IndexingAction.REEMBED:
            assert isinstance(event, ContentChangedEvent)
            await self._reembed(event, product_id)
        elif action is IndexingAction.PAYLOAD_ONLY:
            await self._payload_only(event, product_id)
        else:  # IndexingAction.TOMBSTONE (единственное оставшееся)
            assert isinstance(event, ProductDeletedEvent)
            await self._tombstone(event, product_id)

    async def _full_index(self, snapshot: ProductSnapshot) -> None:
        """Полная индексация: документ → эмбеддинг → upsert."""
        await index_snapshot(
            snapshot,
            index=self._index,
            embedder=self._embedder,
            clock=self._clock,
        )

    async def _repair(self, product_id: ProductId) -> None:
        """Gap-repair: тянет снимок из catalog и индексирует (§6.4)."""
        snapshot = await self._catalog.get_product(product_id)
        if snapshot is None:
            raise ProductNotInCatalog(
                f"Товар отсутствует в catalog: {product_id.value}"
            )
        await self._full_index(snapshot)

    async def _reembed(
        self, event: ContentChangedEvent, product_id: ProductId
    ) -> None:
        """Ре-эмбеддинг: update_vectors + set_payload контент-полей."""
        now = self._clock.now()
        text = compose(
            name=event.name,
            brand=event.brand,
            category=event.category,
            description=event.description,
        )
        [embedding] = await self._embedder.embed_documents([text])
        await self._index.update_vectors(product_id, embedding)
        await self._index.set_payload(
            product_id,
            content_payload(
                name=event.name,
                description=event.description,
                category=event.category,
                brand=event.brand,
                content_hash=ContentHash.of(text.value).value,
                model_version=embedding.model_id.key,
                aggregate_version=event.aggregate_version,
                indexed_at=now,
            ),
        )

    async def _payload_only(
        self, event: CatalogEvent, product_id: ProductId
    ) -> None:
        """Обновление payload без ре-эмбеддинга (commercial или дедуп)."""
        now = self._clock.now()
        if isinstance(event, CommercialChangedEvent):
            fields = commercial_payload(
                pricing=self._build_pricing(event),
                stock=StockLevel(event.stock),
                supplier=event.supplier,
                aggregate_version=event.aggregate_version,
                indexed_at=now,
            )
        else:
            assert isinstance(event, ContentChangedEvent)
            text = compose(
                name=event.name,
                brand=event.brand,
                category=event.category,
                description=event.description,
            )
            fields = content_payload(
                name=event.name,
                description=event.description,
                category=event.category,
                brand=event.brand,
                content_hash=ContentHash.of(text.value).value,
                model_version=self._embedder.model_id.key,
                aggregate_version=event.aggregate_version,
                indexed_at=now,
            )
        await self._index.set_payload(product_id, fields)

    async def _tombstone(
        self, event: ProductDeletedEvent, product_id: ProductId
    ) -> None:
        """Помечает точку удалённой, сохраняя версию (§6.5)."""
        await tombstone(
            product_id,
            index=self._index,
            clock=self._clock,
            version=event.aggregate_version,
        )

    @staticmethod
    def _build_pricing(event: CommercialChangedEvent) -> Pricing:
        """Собирает ``Pricing`` из коммерческого события."""
        currency = Currency(event.currency)
        return Pricing(
            price=Money.of(event.price, currency),
            cost=Money.of(event.cost, currency),
        )
