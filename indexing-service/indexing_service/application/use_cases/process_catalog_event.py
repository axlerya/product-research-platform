"""Use case ``ProcessCatalogEvent`` — оркестратор консюмера (U1).

Читает водяной знак, классифицирует изменение (§6.2) и исполняет нужное
действие над Qdrant. Доменные ошибки (poison) переводит в
``EventValidationError`` (→ DLQ); временные ошибки портов пробрасывает.

Векторы здесь не считаются. Ветки, которым нужен эмбеддинг (created /
content / repair), пишут в Qdrant карточку товара **без** водяных знаков
текста и модели и ставят задание через ``RequestEmbedding`` — дальше
работает embedding-service, а результат применит ``ApplyEmbeddingResult``
(§0, фаза A). Коммерческие изменения, дедуп и удаление идут прямым путём в
Qdrant, мимо embedding-service.
"""

from indexing_service.application.document_builder import to_product_document
from indexing_service.application.dto.embedding_job import EmbeddingJobRequest
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
from indexing_service.application.indexer import tombstone
from indexing_service.application.payload import (
    commercial_payload,
    pending_content_fields,
    pending_payload,
)
from indexing_service.application.ports.catalog_gateway import CatalogGateway
from indexing_service.application.ports.clock import Clock
from indexing_service.application.ports.vector_index import VectorIndex
from indexing_service.application.use_cases.request_embedding import (
    RequestEmbedding,
)
from indexing_service.domain.exceptions import DomainError
from indexing_service.domain.services.change_classifier import (
    IndexingAction,
    classify,
)
from indexing_service.domain.services.document_composer import compose
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.currency import Currency
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.job_status import IndexAction
from indexing_service.domain.value_objects.money import Money
from indexing_service.domain.value_objects.pricing import Pricing
from indexing_service.domain.value_objects.sku import Sku
from indexing_service.domain.value_objects.stock import StockLevel


class ProcessCatalogEvent:
    """Обрабатывает одно событие каталога идемпотентно (§6)."""

    def __init__(
        self,
        *,
        index: VectorIndex,
        request_embedding: RequestEmbedding,
        catalog: CatalogGateway,
        clock: Clock,
        expected_model: str | None = None,
    ) -> None:
        self._index = index
        self._request_embedding = request_embedding
        self._catalog = catalog
        self._clock = clock
        self._expected_model = expected_model

    async def handle(self, event: CatalogEvent) -> IndexingAction:
        """Классифицирует и применяет событие; возвращает действие.

        Raises:
            EventValidationError: Событие нарушает доменные инварианты.
            TransientError: Временный сбой порта (Qdrant/Postgres/catalog).
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
                current_model=self._expected_model,
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
        """Карточка товара в Qdrant + задание на эмбеддинг (фаза A)."""
        document = to_product_document(snapshot)
        await self._index.upsert_payload(
            document.product_id,
            pending_payload(document, indexed_at=self._clock.now()),
        )
        await self._request_embedding.handle(
            EmbeddingJobRequest(
                product_id=document.product_id,
                sku=document.sku,
                aggregate_version=document.aggregate_version,
                content_version=document.aggregate_version,
                content_hash=document.content_hash(),
                text=document.search_text(),
                action=IndexAction.FULL_INDEX,
            )
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
        """Новый текст в payload + задание на пересчёт векторов (фаза A)."""
        text = compose(
            name=event.name,
            brand=event.brand,
            category=event.category,
            description=event.description,
        )
        await self._index.set_payload(
            product_id,
            pending_content_fields(
                name=event.name,
                description=event.description,
                category=event.category,
                brand=event.brand,
                aggregate_version=event.aggregate_version,
                indexed_at=self._clock.now(),
            ),
        )
        await self._request_embedding.handle(
            EmbeddingJobRequest(
                product_id=product_id,
                sku=Sku(event.sku),
                aggregate_version=event.aggregate_version,
                content_version=event.aggregate_version,
                content_hash=ContentHash.of(text.value),
                text=text,
                action=IndexAction.REEMBED,
            )
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
            # Текст тот же — водяные знаки уже стоят, трогать их незачем.
            fields = pending_content_fields(
                name=event.name,
                description=event.description,
                category=event.category,
                brand=event.brand,
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
