"""Unit-тесты ``build_reranker_provider`` — сборка провайдера из настроек."""

from embedding_service.infrastructure.reranker_config import RerankerSettings
from embedding_service.infrastructure.reranking.concurrency import (
    ConcurrencyGuardedRerankerProvider,
)
from embedding_service.infrastructure.reranking.deterministic import (
    DeterministicRerankerProvider,
)
from embedding_service.infrastructure.reranking.factory import (
    build_reranker_provider,
)


class TestBuildRerankerProvider:
    async def test_deterministic_mode_end_to_end(self) -> None:
        settings = RerankerSettings(
            _env_file=None, provider_mode="deterministic", max_batch_size=2
        )
        provider = build_reranker_provider(settings)
        assert isinstance(provider, ConcurrencyGuardedRerankerProvider)
        scores = await provider.rerank("q", ["a", "b", "c"])
        assert len(scores) == 3
        assert provider.model_id.name == "BAAI/bge-reranker-v2-m3"

    async def test_deterministic_provider_probe(self) -> None:
        settings = RerankerSettings(
            _env_file=None, provider_mode="deterministic"
        )
        provider = build_reranker_provider(settings)
        status = await provider.probe()
        assert status.precision == "fake"

    def test_bge_mode_delegates_to_loader(self, monkeypatch) -> None:
        # Ветка реального провайдера: загрузчик torch подменён (без весов).
        called: dict[str, RerankerSettings] = {}

        def _fake_load(settings: RerankerSettings):
            called["settings"] = settings
            return DeterministicRerankerProvider(
                model_id=settings.build_model_id()
            )

        monkeypatch.setattr(
            "embedding_service.infrastructure.reranking.factory._load_bge",
            _fake_load,
        )
        settings = RerankerSettings(
            _env_file=None, provider_mode="bge_reranker"
        )
        provider = build_reranker_provider(settings)
        assert called["settings"] is settings
        assert provider.model_id.name == "BAAI/bge-reranker-v2-m3"
