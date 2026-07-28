"""Composition root: связывает порты application с адаптерами infrastructure.

Единственное место, знающее про все слои. Отсюда фабрики берут ``main``
(HTTP), ``relay_app`` (relay) и ``seed_cli`` (CLI).
"""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from catalog_service.application.ports.csv_row_source import CsvRowSource
from catalog_service.application.ports.read_models import (
    ProductQueryService,
    ReferenceQueryService,
)
from catalog_service.application.price_analysis import AnalyzePrices
from catalog_service.application.use_cases.create_product import CreateProduct
from catalog_service.application.use_cases.delete_product import DeleteProduct
from catalog_service.application.use_cases.seed_catalog import SeedCatalog
from catalog_service.application.use_cases.set_stock import SetStock
from catalog_service.application.use_cases.update_commercial_data import (
    UpdateCommercialData,
)
from catalog_service.application.use_cases.update_metrics import UpdateMetrics
from catalog_service.application.use_cases.update_product_content import (
    UpdateProductContent,
)
from catalog_service.infrastructure.config import Settings, get_settings
from catalog_service.infrastructure.csv.csv_row_source import (
    CsvRowSource as CsvRowSourceImpl,
)
from catalog_service.infrastructure.db.engine import (
    build_engine,
    build_sessionmaker,
)
from catalog_service.infrastructure.db.repositories.query_service import (
    SqlAlchemyProductQueryService,
    SqlAlchemyReferenceQueryService,
)
from catalog_service.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from catalog_service.infrastructure.messaging.broker import (
    RabbitEventPublisher,
    build_broker,
)
from catalog_service.infrastructure.outbox.relay import OutboxPublisher
from catalog_service.infrastructure.services.clock import SystemClock
from catalog_service.infrastructure.services.id_generator import (
    Uuid7Generator,
)


class Container:
    """Фабрики зависимостей сервиса."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: AsyncEngine = build_engine(settings)
        self.sessionmaker: async_sessionmaker = build_sessionmaker(self.engine)
        self.broker = build_broker(settings)
        self._clock = SystemClock()
        self._ids = Uuid7Generator()

    def _uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.sessionmaker)

    def create_product_uc(self) -> CreateProduct:
        return CreateProduct(
            uow=self._uow(),
            clock=self._clock,
            id_gen=self._ids,
            default_currency=self.settings.default_currency,
        )

    def update_content_uc(self) -> UpdateProductContent:
        return UpdateProductContent(
            uow=self._uow(), clock=self._clock, id_gen=self._ids
        )

    def update_commercial_uc(self) -> UpdateCommercialData:
        return UpdateCommercialData(
            uow=self._uow(), clock=self._clock, id_gen=self._ids
        )

    def set_stock_uc(self) -> SetStock:
        return SetStock(uow=self._uow(), clock=self._clock, id_gen=self._ids)

    def update_metrics_uc(self) -> UpdateMetrics:
        return UpdateMetrics(
            uow=self._uow(), clock=self._clock, id_gen=self._ids
        )

    def delete_product_uc(self) -> DeleteProduct:
        return DeleteProduct(
            uow=self._uow(), clock=self._clock, id_gen=self._ids
        )

    def product_query_service(self) -> ProductQueryService:
        return SqlAlchemyProductQueryService(self.sessionmaker)

    def reference_query_service(self) -> ReferenceQueryService:
        return SqlAlchemyReferenceQueryService(self.sessionmaker)

    def analyze_prices(self) -> AnalyzePrices:
        return AnalyzePrices(
            products=self.product_query_service(),
            default_currency=self.settings.default_currency,
        )

    def csv_row_source(self, path: str | Path) -> CsvRowSource:
        return CsvRowSourceImpl(path)

    def seed_catalog(
        self, source: CsvRowSource, *, on_stale: str = "skip"
    ) -> SeedCatalog:
        return SeedCatalog(
            uow=self._uow(),
            source=source,
            clock=self._clock,
            id_gen=self._ids,
            default_currency=self.settings.default_currency,
            on_stale=on_stale,
        )

    def outbox_publisher(self) -> OutboxPublisher:
        return OutboxPublisher(
            self.sessionmaker,
            RabbitEventPublisher(self.broker),
            max_attempts=self.settings.outbox_max_attempts,
            batch_size=self.settings.outbox_batch_size,
        )


def build_container(settings: Settings | None = None) -> Container:
    """Собирает контейнер зависимостей из настроек."""
    return Container(settings or get_settings())
