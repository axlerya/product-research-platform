"""Value object ``ContractVersion`` — версия формата проводов."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContractVersion:
    """Версия формата проводов, независимая от ``model_version``.

    Attributes:
        major: MAJOR (суффикс routing key ``.vN`` / gRPC ``package``).
        minor: MINOR (tolerant-совместимое расширение конверта).
    """

    major: int
    minor: int

    @property
    def wire(self) -> str:
        """Semver-строка формата, например ``"1.0"``."""
        return f"{self.major}.{self.minor}"
