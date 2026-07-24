"""Value object RunError — структурированная ошибка прогона."""

from dataclasses import dataclass

from research_agent_service.domain.value_objects.enums import (
    ErrorCategory,
    ErrorCode,
    RunStage,
)


@dataclass(frozen=True, slots=True)
class RunError:
    """Код, категория, стадия и человекочитаемое сообщение ошибки.

    Attributes:
        code: Машиночитаемый код ошибки.
        category: Категория для маршрутизации и метрик.
        stage: Стадия прогона, на которой произошёл сбой.
        message: Человекочитаемое описание.
    """

    code: ErrorCode
    category: ErrorCategory
    stage: RunStage
    message: str
