"""Use case U4 ``WarmupModel`` — прогрев и probe для readiness."""

from embedding_service.application.dto import ProviderStatus
from embedding_service.application.ports.embedding_provider import (
    EmbeddingProvider,
)


class WarmupModel:
    """Прогревает модель и возвращает её статус (для readiness §8)."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider

    async def handle(self) -> ProviderStatus:
        await self._provider.warmup()
        return await self._provider.probe()
