"""Value object Citation — проверяемый источник факта в ответе."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from research_agent_service.domain.exceptions import InvalidCitation
from research_agent_service.domain.value_objects.enums import CitationType


@dataclass(frozen=True, slots=True)
class Citation:
    """Источник факта: тип, ссылка (ref), заголовок, сниппет, позиция.

    ref связывает цитату с реально полученным фактом (sku для product,
    URL для web, analysis_ref для price_analysis); принадлежность ref
    множеству извлечённых фактов проверяется в application-слое.

    Attributes:
        source_type: Тип источника.
        ref: Ссылка на факт.
        title: Заголовок источника.
        snippet: Фрагмент (для web — непроверяемый текст провайдера).
        position: Позиция в списке источников (>= 0).
        retrieved_at: Момент получения факта.
        score: Скор релевантности, если применимо.
    """

    source_type: CitationType
    ref: str
    title: str
    snippet: str
    position: int
    retrieved_at: datetime
    score: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.ref.strip():
            raise InvalidCitation("Citation.ref не может быть пустым")
        if self.position < 0:
            raise InvalidCitation("Citation.position не может быть < 0")
