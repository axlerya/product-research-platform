"""Use case U5 ``DescribeModel`` — статус модели для диагностики."""

from embedding_service.application.dto import ProviderStatus
from embedding_service.application.ports.embedding_provider import (
    EmbeddingProvider,
)


class DescribeModel:
    """Возвращает статус провайдера (model_key/device/precision/degraded)."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider

    async def handle(self) -> ProviderStatus:
        return await self._provider.probe()
