"""Value object Degradation — деградация зависимости в прогоне."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Degradation:
    """Отказавшая зависимость и причина деградации.

    Attributes:
        dependency: Имя зависимости (например, ``"reranker"``).
        reason: Причина (например, ``"unimplemented"``).
    """

    dependency: str
    reason: str
