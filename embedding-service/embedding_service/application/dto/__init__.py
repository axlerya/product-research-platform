"""DTO слоя application (frozen dataclass, не Pydantic)."""

from embedding_service.application.dto.commands import (
    DocumentsGenerated,
    EmbedDocumentsCommand,
    EmbedQueriesQuery,
    EmbedQueryQuery,
)
from embedding_service.application.dto.provider_status import ProviderStatus

__all__ = [
    "DocumentsGenerated",
    "EmbedDocumentsCommand",
    "EmbedQueriesQuery",
    "EmbedQueryQuery",
    "ProviderStatus",
]
