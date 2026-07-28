"""Read-side: SQL-реализация сервисов запросов (CQRS-lite).

Денормализованные SELECT c JOIN справочников, без гидрации доменного
агрегата. Значения фильтров — только через bound-параметры; сортировка —
по whitelist (защита от инъекций).
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from catalog_service.application.dto.queries import (
    SORT_COLUMNS,
    PriceAnalysisSelector,
    ProductSearchQuery,
)
from catalog_service.application.dto.views import (
    CategoryMarginRow,
    MarginView,
    MoneyView,
    Page,
    ProductBatchView,
    ProductView,
    ReferenceView,
)

_SELECT = """
SELECT p.id, p.sku, p.name, p.description,
       c.name AS category, b.name AS brand, s.name AS supplier,
       p.price_amount, p.cost_amount, p.currency, p.stock_quantity,
       p.sales_per_month, p.avg_rating, p.review_count, p.margin_percent,
       p.source_updated_at, p.version, p.is_deleted,
       p.created_at, p.updated_at
FROM products p
JOIN categories c ON c.id = p.category_id
JOIN brands b ON b.id = p.brand_id
JOIN suppliers s ON s.id = p.supplier_id
"""


def _to_view(row) -> ProductView:
    currency = row.currency
    price = row.price_amount
    cost = row.cost_amount
    return ProductView(
        id=row.id,
        sku=row.sku,
        name=row.name,
        description=row.description,
        category=row.category,
        brand=row.brand,
        supplier=row.supplier,
        price=MoneyView(price, currency),
        cost=MoneyView(cost, currency),
        stock=row.stock_quantity,
        is_in_stock=row.stock_quantity > 0,
        sales_per_month=row.sales_per_month,
        avg_rating=row.avg_rating,
        review_count=row.review_count,
        margin=MarginView(
            MoneyView(price - cost, currency), row.margin_percent
        ),
        source_updated_at=row.source_updated_at,
        version=row.version,
        is_deleted=row.is_deleted,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _order_by(sort: str) -> str:
    descending = sort.startswith("-")
    column = SORT_COLUMNS.get(sort.lstrip("-"), "created_at")
    return f"p.{column} {'DESC' if descending else 'ASC'}"


def _normalize(skus: Sequence[str]) -> list[str]:
    """Нормализует артикулы как домен (strip+upper), сохраняя порядок."""
    return list(dict.fromkeys(sku.strip().upper() for sku in skus))


def _filters(
    query: ProductSearchQuery | PriceAnalysisSelector,
) -> tuple[list[str], dict[str, Any]]:
    """Условия и параметры общих фасетов (поиск и срез анализа одинаковы)."""
    conditions: list[str] = []
    params: dict[str, Any] = {}
    if not query.include_deleted:
        conditions.append("p.is_deleted = FALSE")
    if query.text:
        conditions.append("(p.name ILIKE :text OR p.description ILIKE :text)")
        params["text"] = f"%{query.text}%"
    for field, column in (
        ("category", "c.name"),
        ("brand", "b.name"),
        ("supplier", "s.name"),
    ):
        value = getattr(query, field)
        if value is not None:
            conditions.append(f"{column} = :{field}")
            params[field] = value
    if query.price_min is not None:
        conditions.append("p.price_amount >= :price_min")
        params["price_min"] = query.price_min
    if query.price_max is not None:
        conditions.append("p.price_amount <= :price_max")
        params["price_max"] = query.price_max
    if query.in_stock is True:
        conditions.append("p.stock_quantity > 0")
    elif query.in_stock is False:
        conditions.append("p.stock_quantity = 0")
    if query.min_rating is not None:
        conditions.append("p.avg_rating >= :min_rating")
        params["min_rating"] = query.min_rating
    if query.margin_min is not None:
        conditions.append("p.margin_percent >= :margin_min")
        params["margin_min"] = query.margin_min
    if query.margin_max is not None:
        conditions.append("p.margin_percent <= :margin_max")
        params["margin_max"] = query.margin_max
    return conditions, params


class SqlAlchemyProductQueryService:
    """Чтение товаров денормализованным SQL."""

    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def get(
        self,
        *,
        product_id: UUID | None = None,
        sku: str | None = None,
        include_deleted: bool = False,
    ) -> ProductView | None:
        conditions: list[str] = []
        params: dict[str, Any] = {}
        if product_id is not None:
            conditions.append("p.id = :pid")
            params["pid"] = product_id
        if sku is not None:
            conditions.append("p.sku = :sku")
            params["sku"] = sku.strip().upper()
        if not include_deleted:
            conditions.append("p.is_deleted = FALSE")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        async with self._sessionmaker() as session:
            row = (await session.execute(text(_SELECT + where), params)).first()
        return _to_view(row) if row is not None else None

    async def get_many(
        self, skus: Sequence[str], *, include_deleted: bool = False
    ) -> ProductBatchView:
        requested = _normalize(skus)
        if not requested:
            return ProductBatchView(products=(), missing_skus=())
        conditions = ["p.sku IN :skus"]
        if not include_deleted:
            conditions.append("p.is_deleted = FALSE")
        statement = text(
            _SELECT + " WHERE " + " AND ".join(conditions)
        ).bindparams(bindparam("skus", expanding=True))
        async with self._sessionmaker() as session:
            rows = (await session.execute(statement, {"skus": requested})).all()
        found = {row.sku: _to_view(row) for row in rows}
        return ProductBatchView(
            # Порядок ответа — порядок запроса: клиент сопоставляет позиции.
            products=tuple(found[sku] for sku in requested if sku in found),
            missing_skus=tuple(sku for sku in requested if sku not in found),
        )

    async def select_for_analysis(
        self, selector: PriceAnalysisSelector
    ) -> tuple[ProductView, ...]:
        conditions, params = _filters(selector)
        requested = _normalize(selector.skus)
        if requested:
            conditions.append("p.sku IN :skus")
            params["skus"] = requested
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        # Без пагинации: статистика считается по всему срезу целиком.
        statement = text(f"{_SELECT}{where} ORDER BY p.sku")
        if requested:
            statement = statement.bindparams(bindparam("skus", expanding=True))
        async with self._sessionmaker() as session:
            rows = (await session.execute(statement, params)).all()
        return tuple(_to_view(row) for row in rows)

    async def search(self, query: ProductSearchQuery) -> Page[ProductView]:
        conditions, params = _filters(query)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        list_sql = (
            f"{_SELECT}{where} ORDER BY {_order_by(query.sort)} "
            "LIMIT :limit OFFSET :offset"
        )
        count_sql = (
            "SELECT count(*) FROM products p "
            "JOIN categories c ON c.id = p.category_id "
            "JOIN brands b ON b.id = p.brand_id "
            "JOIN suppliers s ON s.id = p.supplier_id" + where
        )
        async with self._sessionmaker() as session:
            rows = (
                await session.execute(
                    text(list_sql),
                    {**params, "limit": query.limit, "offset": query.offset},
                )
            ).all()
            total = (
                await session.execute(text(count_sql), params)
            ).scalar_one()
        return Page(
            items=tuple(_to_view(row) for row in rows),
            total=total,
            limit=query.limit,
            offset=query.offset,
        )

    async def margin_by_category(
        self, *, include_deleted: bool = False
    ) -> tuple[CategoryMarginRow, ...]:
        where = "" if include_deleted else " WHERE p.is_deleted = FALSE"
        sql = (
            "SELECT c.name AS category, count(*) AS cnt, "
            "round(avg(p.margin_percent), 2) AS avg_m, "
            "min(p.margin_percent) AS min_m, max(p.margin_percent) AS max_m "
            "FROM products p JOIN categories c ON c.id = p.category_id"
            f"{where} GROUP BY c.name ORDER BY c.name"
        )
        async with self._sessionmaker() as session:
            rows = (await session.execute(text(sql))).all()
        return tuple(
            CategoryMarginRow(
                category=row.category,
                product_count=row.cnt,
                avg_margin_percent=row.avg_m,
                min_margin_percent=row.min_m,
                max_margin_percent=row.max_m,
            )
            for row in rows
        )


class SqlAlchemyReferenceQueryService:
    """Чтение справочников с числом активных товаров."""

    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def _list(self, table: str, fk: str) -> tuple[ReferenceView, ...]:
        sql = (
            f"SELECT r.id, r.name, "
            f"count(p.id) FILTER (WHERE p.is_deleted = FALSE) AS cnt "
            f"FROM {table} r LEFT JOIN products p ON p.{fk} = r.id "
            f"GROUP BY r.id, r.name ORDER BY r.name"
        )
        async with self._sessionmaker() as session:
            rows = (await session.execute(text(sql))).all()
        return tuple(
            ReferenceView(id=row.id, name=row.name, product_count=row.cnt)
            for row in rows
        )

    async def list_categories(self) -> tuple[ReferenceView, ...]:
        return await self._list("categories", "category_id")

    async def list_brands(self) -> tuple[ReferenceView, ...]:
        return await self._list("brands", "brand_id")

    async def list_suppliers(self) -> tuple[ReferenceView, ...]:
        return await self._list("suppliers", "supplier_id")
