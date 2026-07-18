"""Use case ``SeedCatalog`` (C7) — идемпотентный seed из CSV.

Оркестратор поверх тех же доменных методов и outbox, что и админ-API:
для каждой строки — upsert по SKU, агрегат сам классифицирует diff в
события. Повторный прогон неизменного файла даёт ноль новых событий.

Примечание: изоляция битой строки savepoint'ом и батчинг коммитов —
инфраструктурная деталь (savepoint на строку в реальном UnitOfWork).
Здесь прогон идёт в одной транзакции; грязные строки отсеиваются на
этапе парсинга (до мутаций), поэтому не «отравляют» транзакцию.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from catalog_service.application.dto.seed import (
    RawProductRow,
    RowError,
    RowOutcome,
    SeedReport,
)
from catalog_service.application.event_mapping import build_messages
from catalog_service.application.ports.csv_row_source import CsvRowSource
from catalog_service.application.ports.services import Clock, IdGenerator
from catalog_service.application.ports.uow import UnitOfWork
from catalog_service.domain.entities.product import Product
from catalog_service.domain.events import DomainEvent
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

_CONTENT_KEY = "catalog.product.content_changed"
_COMMERCIAL_KEY = "catalog.product.commercial_data_changed"


@dataclass(frozen=True, slots=True)
class _ParsedRow:
    """Строка CSV после приведения типов и построения доменных VO."""

    sku: Sku
    name: str
    description: str
    category_name: str
    brand_name: str
    supplier_name: str
    pricing: Pricing
    stock: StockLevel
    metrics: ProductMetrics
    source_updated_at: date | None


class _RowParseError(Exception):
    """Внутренняя ошибка парсинга строки (несёт ``RowError``)."""

    def __init__(self, row_error: RowError) -> None:
        super().__init__(row_error.message)
        self.row_error = row_error


def _required(field_name: str, value: str | None) -> str:
    if value is None or not value.strip():
        raise ValueError(f"Пустое обязательное поле: {field_name}")
    return value.strip()


def _parse_date(value: str | None) -> date | None:
    if value is None or not value.strip():
        return None
    return date.fromisoformat(value.strip())


def _parse_row(raw: RawProductRow, currency: Currency) -> _ParsedRow:
    """Строит ``_ParsedRow`` из сырой строки.

    Raises:
        _RowParseError: Значение не распарсилось (``parse``) или не прошло
            доменную валидацию (``domain``).
    """
    try:
        parsed = _ParsedRow(
            sku=Sku(_required("артикул", raw.sku)),
            name=_required("название", raw.name),
            description=(raw.description or "").strip(),
            category_name=_required("категория", raw.category_name),
            brand_name=_required("бренд", raw.brand_name),
            supplier_name=_required("поставщик", raw.supplier_name),
            pricing=Pricing(
                price=Money.of(Decimal(_required("цена", raw.price)), currency),
                cost=Money.of(
                    Decimal(_required("себестоимость", raw.cost)), currency
                ),
            ),
            stock=StockLevel(int(_required("остаток", raw.stock))),
            metrics=ProductMetrics(
                sales_per_month=int(_required("продажи", raw.sales_per_month)),
                avg_rating=Rating(
                    Decimal(_required("рейтинг", raw.avg_rating))
                ),
                review_count=int(_required("отзывы", raw.review_count)),
            ),
            source_updated_at=_parse_date(raw.source_updated_at),
        )
    except DomainError as exc:
        raise _RowParseError(
            RowError(
                line_no=raw.line_no,
                sku=raw.sku,
                kind="domain",
                message=str(exc),
            )
        ) from exc
    except (InvalidOperation, ValueError) as exc:
        raise _RowParseError(
            RowError(
                line_no=raw.line_no, sku=raw.sku, kind="parse", message=str(exc)
            )
        ) from exc
    return parsed


def _classify(events: list[DomainEvent]) -> RowOutcome:
    """Определяет исход строки по набору эмитированных событий."""
    keys = {e.routing_key for e in events}
    has_content = _CONTENT_KEY in keys
    has_commercial = _COMMERCIAL_KEY in keys
    if has_content and has_commercial:
        return RowOutcome.BOTH
    if has_content:
        return RowOutcome.CONTENT_CHANGED
    if has_commercial:
        return RowOutcome.COMMERCIAL_CHANGED
    return RowOutcome.METRICS_ONLY


class SeedCatalog:
    """Идемпотентно наполняет каталог из CSV через доменные методы."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        source: CsvRowSource,
        clock: Clock,
        id_gen: IdGenerator,
        default_currency: str,
        on_stale: str = "skip",
    ) -> None:
        self._uow = uow
        self._source = source
        self._clock = clock
        self._id_gen = id_gen
        self._default_currency = default_currency
        self._on_stale = on_stale

    async def execute(self) -> SeedReport:
        """Прогоняет seed и возвращает отчёт."""
        report = SeedReport()
        seen: set[str] = set()
        currency = Currency(self._default_currency)
        now = self._clock.now()
        async with self._uow as uow:
            for raw in self._source:
                report.total += 1
                try:
                    parsed = _parse_row(raw, currency)
                except _RowParseError as exc:
                    report.errors.append(exc.row_error)
                    continue
                if parsed.sku.value in seen:
                    report.errors.append(
                        RowError(
                            line_no=raw.line_no,
                            sku=parsed.sku.value,
                            kind="duplicate_in_file",
                            message="Дубликат SKU в файле",
                        )
                    )
                    continue
                seen.add(parsed.sku.value)
                outcome, events = await self._apply(parsed, uow, now)
                report.record(outcome)
                report.events_emitted += len(events)
            await uow.commit()
        return report

    async def _apply(
        self, parsed: _ParsedRow, uow: UnitOfWork, now: datetime
    ) -> tuple[RowOutcome, list[DomainEvent]]:
        existing = await uow.products.get_by_sku(parsed.sku)
        if existing is None:
            product = await self._create(parsed, uow, now)
            events = product.collect_events()
            await uow.outbox.add_many(
                build_messages(events, product, self._id_gen)
            )
            return RowOutcome.CREATED, events

        if self._skip_by_freshness(existing, parsed):
            return RowOutcome.SKIPPED_STALE, []

        expected = existing.version
        category = await uow.categories.get_or_create(parsed.category_name)
        brand = await uow.brands.get_or_create(parsed.brand_name)
        supplier = await uow.suppliers.get_or_create(parsed.supplier_name)
        existing.change_content(
            name=parsed.name,
            description=parsed.description,
            category=CategoryRef(category.id, category.name),
            brand=BrandRef(brand.id, brand.name),
            now=now,
        )
        existing.change_commercial(
            pricing=parsed.pricing,
            stock=parsed.stock,
            supplier=SupplierRef(supplier.id, supplier.name),
            now=now,
        )
        existing.update_metrics(parsed.metrics, now=now)
        events = existing.collect_events()
        if not events and existing.version == expected:
            return RowOutcome.UNCHANGED, []

        await uow.products.update(existing, expected_version=expected)
        await uow.outbox.add_many(
            build_messages(events, existing, self._id_gen)
        )
        return _classify(events), events

    async def _create(
        self, parsed: _ParsedRow, uow: UnitOfWork, now: datetime
    ) -> Product:
        category = await uow.categories.get_or_create(parsed.category_name)
        brand = await uow.brands.get_or_create(parsed.brand_name)
        supplier = await uow.suppliers.get_or_create(parsed.supplier_name)
        product = Product.create(
            id=self._id_gen.new_product_id(),
            sku=parsed.sku,
            name=parsed.name,
            description=parsed.description,
            category=CategoryRef(category.id, category.name),
            brand=BrandRef(brand.id, brand.name),
            supplier=SupplierRef(supplier.id, supplier.name),
            pricing=parsed.pricing,
            stock=parsed.stock,
            metrics=parsed.metrics,
            source_updated_at=parsed.source_updated_at,
            now=now,
        )
        await uow.products.add(product)
        return product

    def _skip_by_freshness(self, existing: Product, parsed: _ParsedRow) -> bool:
        """Пропускать ли строку: CSV не новее хранимого (защита правок)."""
        if self._on_stale != "skip":
            return False
        if (
            parsed.source_updated_at is None
            or existing.source_updated_at is None
        ):
            return False
        return parsed.source_updated_at <= existing.source_updated_at
