"""Тесты реального CSV-reader."""

from pathlib import Path

import pytest

from catalog_service.infrastructure.csv.csv_row_source import (
    CsvRowSource,
    SeedFileError,
)

_HEADER = (
    "артикул,название_товара,категория,бренд,описание,текущая_цена,"
    "себестоимость,количество_на_складе,продажи_в_месяц,средний_рейтинг,"
    "количество_отзывов,поставщик,последнее_обновление"
)
_LINE = (
    "PROD-001,Наушники,Электроника,AudioMax,Опис,129.99,65.00,245,87,"
    "4.5,1243,TechSupply Co,2024-03-15"
)


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "catalog.csv"
    path.write_text(content, encoding="utf-8-sig")
    return path


def test_reads_rows_with_russian_headers(tmp_path):
    path = _write(tmp_path, f"{_HEADER}\n{_LINE}\n")
    rows = list(CsvRowSource(path))
    assert len(rows) == 1
    row = rows[0]
    assert row.line_no == 2
    assert row.sku == "PROD-001"
    assert row.name == "Наушники"
    assert row.category_name == "Электроника"
    assert row.price == "129.99"
    assert row.source_updated_at == "2024-03-15"


def test_missing_columns_raises(tmp_path):
    path = _write(tmp_path, "артикул,название_товара\nPROD-1,X\n")
    with pytest.raises(SeedFileError):
        list(CsvRowSource(path))
