"""Value object ``TokenCount`` — число токенов текста."""

from dataclasses import dataclass

from embedding_service.domain.exceptions import InvalidVectorError


@dataclass(frozen=True, slots=True)
class TokenCount:
    """Неотрицательное число токенов.

    Attributes:
        value: Число токенов (``>= 0``).
    """

    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise InvalidVectorError(
                f"Число токенов не может быть отрицательным: {self.value}"
            )
