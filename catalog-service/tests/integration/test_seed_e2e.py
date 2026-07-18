"""E2E: seed реального products_catalog_ru.csv в Postgres через bootstrap."""

from pathlib import Path

import pytest
from sqlalchemy import text

from catalog_service.bootstrap import build_container
from catalog_service.infrastructure.config import Settings
from catalog_service.infrastructure.csv.csv_row_source import CsvRowSource

pytestmark = pytest.mark.integration

_CSV = Path(__file__).resolve().parents[3] / "products_catalog_ru.csv"


@pytest.mark.skipif(
    not _CSV.exists(), reason="products_catalog_ru.csv отсутствует (gitignore)"
)
async def test_seed_real_catalog(sm, database_url):
    container = build_container(Settings(database_url=database_url))

    report = await container.seed_catalog(CsvRowSource(_CSV)).execute()
    assert report.total == 105
    assert report.created == 105
    assert report.errors == []
    assert report.events_emitted == 105

    async with sm() as session:
        products = (
            await session.execute(text("SELECT count(*) FROM products"))
        ).scalar_one()
        outbox = (
            await session.execute(text("SELECT count(*) FROM outbox"))
        ).scalar_one()
    assert products == 105
    assert outbox == 105

    rerun = await container.seed_catalog(CsvRowSource(_CSV)).execute()
    assert rerun.created == 0
    assert rerun.events_emitted == 0
