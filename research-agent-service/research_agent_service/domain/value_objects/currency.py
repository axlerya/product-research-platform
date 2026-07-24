"""Value object Currency — код валюты ISO-4217 alpha-3."""

import re
from dataclasses import dataclass

from research_agent_service.domain.exceptions import InvalidCurrency

_ISO_4217_ALPHA3 = re.compile(r"[A-Z]{3}")


@dataclass(frozen=True, slots=True)
class Currency:
    """Код валюты из трёх заглавных латинских букв.

    Attributes:
        code: Трёхбуквенный код, например ``"RUB"``.
    """

    code: str

    def __post_init__(self) -> None:
        if not _ISO_4217_ALPHA3.fullmatch(self.code):
            raise InvalidCurrency(
                f"Код валюты должен быть ISO-4217 alpha-3: {self.code!r}"
            )
