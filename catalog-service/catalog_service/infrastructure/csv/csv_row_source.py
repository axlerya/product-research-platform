"""Реальный CSV-reader: русские заголовки -> ``RawProductRow``.

Читается строго ``utf-8-sig`` (BOM-устойчиво): системная локаль ломает
кириллические заголовки. Приведение типов НЕ здесь — оно в прикладном
слое (``SeedCatalog``), сюда отдаются сырые строки.
"""

import csv
from collections.abc import Iterator
from pathlib import Path

from catalog_service.application.dto.seed import RawProductRow

COLUMN_MAP: dict[str, str] = {
    "артикул": "sku",
    "название_товара": "name",
    "категория": "category_name",
    "бренд": "brand_name",
    "описание": "description",
    "текущая_цена": "price",
    "себестоимость": "cost",
    "количество_на_складе": "stock",
    "продажи_в_месяц": "sales_per_month",
    "средний_рейтинг": "avg_rating",
    "количество_отзывов": "review_count",
    "поставщик": "supplier_name",
    "последнее_обновление": "source_updated_at",
}


class SeedFileError(Exception):
    """Файл нечитаем/битый как целое (не «грязная строка»)."""


class CsvRowSource:
    """Ленивый источник строк CSV товаров."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def __iter__(self) -> Iterator[RawProductRow]:
        with self._path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = set(reader.fieldnames or ())
            missing = set(COLUMN_MAP) - headers
            if missing:
                raise SeedFileError(
                    f"В CSV отсутствуют колонки: {sorted(missing)}"
                )
            for line_no, row in enumerate(reader, start=2):
                yield RawProductRow(
                    line_no=line_no,
                    sku=row.get("артикул"),
                    name=row.get("название_товара"),
                    description=row.get("описание"),
                    category_name=row.get("категория"),
                    brand_name=row.get("бренд"),
                    price=row.get("текущая_цена"),
                    cost=row.get("себестоимость"),
                    stock=row.get("количество_на_складе"),
                    sales_per_month=row.get("продажи_в_месяц"),
                    avg_rating=row.get("средний_рейтинг"),
                    review_count=row.get("количество_отзывов"),
                    supplier_name=row.get("поставщик"),
                    source_updated_at=row.get("последнее_обновление"),
                )
