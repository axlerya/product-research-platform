"""Value object ``EmbeddingKind`` — ось разделения document/query."""

from enum import Enum


class EmbeddingKind(Enum):
    """Тип текста. Математика одна; различаются лимиты, SLA, транспорт."""

    DOCUMENT = "document"
    QUERY = "query"
