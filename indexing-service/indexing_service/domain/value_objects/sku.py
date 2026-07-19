"""Value object ``Sku`` — артикул (нормализуемый бизнес-ключ)."""

import re
from dataclasses import dataclass

from indexing_service.domain.exceptions import InvalidSku

_SKU_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9-]{1,62}[A-Z0-9]")


@dataclass(frozen=True, slots=True)
class Sku:
    """Артикул товара.

    Нормализуется как ``strip().upper()``; сравнение и хеш — по значению.
    Домен не привязан к префиксу ``PROD``.

    Attributes:
        value: Нормализованное значение артикула.
    """

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if not _SKU_PATTERN.fullmatch(normalized):
            raise InvalidSku(f"Некорректный артикул: {self.value!r}")
        object.__setattr__(self, "value", normalized)
