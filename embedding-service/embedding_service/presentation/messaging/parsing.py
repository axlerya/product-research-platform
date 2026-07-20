"""Маппинг конверта команды в прикладной DTO (домен не знает про Pydantic)."""

from embedding_service.application.dto import (
    EmbedDocumentsCommand,
    RawTextItem,
)
from embedding_service.presentation.messaging.schemas import RequestedEnvelope


def to_command(envelope: RequestedEnvelope) -> EmbedDocumentsCommand:
    """Конверт → ``EmbedDocumentsCommand`` (сырые items для партиала)."""
    return EmbedDocumentsCommand(
        request_id=str(envelope.data.request_id),
        items=tuple(
            RawTextItem(text_id=item.text_id, text=item.text)
            for item in envelope.data.items
        ),
        return_dense=envelope.data.return_dense,
        return_sparse=envelope.data.return_sparse,
    )
