"""Порт источника строк CSV для seed."""

from collections.abc import Iterator
from typing import Protocol

from catalog_service.application.dto.seed import RawProductRow


class CsvRowSource(Protocol):
    """Ленивый источник сырых строк CSV.

    Реализация в инфраструктуре знает про кодировку, разделитель и карту
    заголовков; наружу отдаёт ``RawProductRow`` (строки без приведения).
    """

    def __iter__(self) -> Iterator[RawProductRow]:
        """Итерирует строки файла (без загрузки всего файла в память)."""
        ...
