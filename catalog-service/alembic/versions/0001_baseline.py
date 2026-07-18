"""baseline: каталог, справочники, outbox

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-19

Схема каталога: справочники, товары (с GENERATED-колонкой маржи,
уникальным SKU включая soft-deleted, trgm/partial-индексами) и outbox.
Механика relay (backoff-колонки, NOTIFY-триггер) — в следующей миграции.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    for table in ("categories", "brands", "suppliers"):
        op.execute(
            f"""
            CREATE TABLE {table} (
              id         UUID PRIMARY KEY,
              name       VARCHAR(200) NOT NULL,
              created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
              CONSTRAINT uq_{table}_name UNIQUE (name)
            )
            """
        )

    op.execute(
        """
        CREATE TABLE products (
          id                UUID PRIMARY KEY,
          sku               VARCHAR(64)  NOT NULL,
          name              VARCHAR(500) NOT NULL,
          description       TEXT         NOT NULL DEFAULT '',
          category_id       UUID NOT NULL,
          brand_id          UUID NOT NULL,
          supplier_id       UUID NOT NULL,
          price_amount      NUMERIC(12,2) NOT NULL,
          cost_amount       NUMERIC(12,2) NOT NULL,
          currency          CHAR(3)       NOT NULL,
          stock_quantity    INTEGER       NOT NULL,
          sales_per_month   INTEGER       NOT NULL DEFAULT 0,
          avg_rating        NUMERIC(3,2)  NOT NULL DEFAULT 0,
          review_count      INTEGER       NOT NULL DEFAULT 0,
          source_updated_at DATE,
          version           INTEGER       NOT NULL DEFAULT 1,
          is_deleted        BOOLEAN       NOT NULL DEFAULT FALSE,
          created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
          updated_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
          deleted_at        TIMESTAMPTZ,
          margin_percent    NUMERIC(5,2) GENERATED ALWAYS AS (
                              CASE WHEN price_amount > 0
                                   THEN round(
                                     (price_amount - cost_amount)
                                     / price_amount * 100, 2)
                                   ELSE NULL END) STORED,
          CONSTRAINT uq_products_sku UNIQUE (sku),
          CONSTRAINT fk_products_category_id_categories
            FOREIGN KEY (category_id) REFERENCES categories(id),
          CONSTRAINT fk_products_brand_id_brands
            FOREIGN KEY (brand_id) REFERENCES brands(id),
          CONSTRAINT fk_products_supplier_id_suppliers
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
          CONSTRAINT ck_products_price_non_negative
            CHECK (price_amount >= 0),
          CONSTRAINT ck_products_cost_non_negative
            CHECK (cost_amount >= 0),
          CONSTRAINT ck_products_stock_non_negative
            CHECK (stock_quantity >= 0),
          CONSTRAINT ck_products_sales_non_negative
            CHECK (sales_per_month >= 0),
          CONSTRAINT ck_products_review_count_non_negative
            CHECK (review_count >= 0),
          CONSTRAINT ck_products_rating_range
            CHECK (avg_rating >= 0 AND avg_rating <= 5),
          CONSTRAINT ck_products_currency_len
            CHECK (char_length(currency) = 3)
        )
        """
    )

    op.execute("CREATE INDEX ix_products_category_id ON products(category_id)")
    op.execute("CREATE INDEX ix_products_brand_id ON products(brand_id)")
    op.execute("CREATE INDEX ix_products_supplier_id ON products(supplier_id)")
    op.execute(
        "CREATE INDEX ix_products_active ON products(created_at DESC) "
        "WHERE is_deleted = FALSE"
    )
    op.execute(
        "CREATE INDEX ix_products_price ON products(price_amount) "
        "WHERE is_deleted = FALSE"
    )
    op.execute(
        "CREATE INDEX ix_products_rating ON products(avg_rating) "
        "WHERE is_deleted = FALSE"
    )
    op.execute(
        "CREATE INDEX ix_products_margin ON products(margin_percent) "
        "WHERE is_deleted = FALSE"
    )
    op.execute(
        "CREATE INDEX ix_products_in_stock ON products(id) "
        "WHERE is_deleted = FALSE AND stock_quantity > 0"
    )
    op.execute(
        "CREATE INDEX ix_products_category_price "
        "ON products(category_id, price_amount) WHERE is_deleted = FALSE"
    )
    op.execute(
        "CREATE INDEX ix_products_search_trgm ON products "
        "USING gin ((name || ' ' || description) gin_trgm_ops)"
    )

    op.execute(
        """
        CREATE TABLE outbox (
          id                UUID PRIMARY KEY,
          aggregate_type    TEXT    NOT NULL,
          aggregate_id      UUID    NOT NULL,
          event_type        TEXT    NOT NULL,
          event_version     INTEGER NOT NULL DEFAULT 1,
          aggregate_version INTEGER NOT NULL,
          payload           JSONB   NOT NULL,
          headers           JSONB   NOT NULL DEFAULT '{}'::jsonb,
          occurred_at       TIMESTAMPTZ NOT NULL,
          created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
          published_at      TIMESTAMPTZ,
          attempts          INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_outbox_pending ON outbox(id) "
        "WHERE published_at IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_outbox_aggregate "
        "ON outbox(aggregate_id, aggregate_version)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS outbox")
    op.execute("DROP TABLE IF EXISTS products")
    op.execute("DROP TABLE IF EXISTS suppliers")
    op.execute("DROP TABLE IF EXISTS brands")
    op.execute("DROP TABLE IF EXISTS categories")
