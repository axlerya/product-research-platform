"""Unit-тесты graceful degrade reranker в composition root.

Сбой создания reranker-провайдера не должен ронять embedding-сервис: reranker
остаётся недоступным, его health — ``NOT_SERVING`` (а ``Rerank`` отвечает
``UNAVAILABLE``, т.к. servicer всё равно регистрируется). Выключенный reranker
провайдер не создаёт вовсе.
"""

from embedding_service import bootstrap, main
from embedding_service.bootstrap import build_deps
from embedding_service.infrastructure.config import Settings
from embedding_service.infrastructure.reranker_config import RerankerSettings
from embedding_service.presentation.grpc.health import NOT_SERVING

_RERANKER_SERVICE = "reranker.v1.RerankerService"


def _settings() -> Settings:
    return Settings(_env_file=None, provider_mode="deterministic", dim=8)


def _reranker_settings(*, enabled: bool) -> RerankerSettings:
    return RerankerSettings(
        _env_file=None,
        enabled=enabled,
        provider_mode="deterministic",
        max_documents=10,
    )


def _boom(settings: RerankerSettings) -> None:
    """Имитация сбоя загрузки весов bge-reranker-v2-m3."""
    raise RuntimeError("не найдены веса BAAI/bge-reranker-v2-m3")


class _FakeHealth:
    """Перехватывает вызовы ``HealthServicer.set`` без поднятия сервера."""

    def __init__(self) -> None:
        self.statuses: list[tuple[str, object]] = []

    async def set(self, service: str, status: object) -> None:
        self.statuses.append((service, status))


class TestDisabledReranker:
    def test_disabled_does_not_build_provider(self, monkeypatch) -> None:
        calls: list[RerankerSettings] = []

        def _spy(settings: RerankerSettings) -> None:
            calls.append(settings)
            raise AssertionError("провайдер не должен создаваться")

        monkeypatch.setattr(bootstrap, "build_reranker_provider", _spy)

        deps = build_deps(_settings(), _reranker_settings(enabled=False))

        assert calls == []
        assert deps.reranker_provider is None
        assert deps.rerank_documents is None
        assert deps.reranker_metrics is None
        assert deps.reranker_enabled is False
        assert deps.reranker_configured is False

    async def test_disabled_prepare_returns_no_servicer(self) -> None:
        deps = build_deps(_settings(), _reranker_settings(enabled=False))
        health = _FakeHealth()

        servicer = await main._prepare_reranker(deps, health, {"value": False})

        # RerankerService не регистрируется → Rerank остаётся UNIMPLEMENTED.
        assert servicer is None
        assert health.statuses == []


class TestProviderBuildFailure:
    def test_build_failure_does_not_break_startup(self, monkeypatch) -> None:
        monkeypatch.setattr(bootstrap, "build_reranker_provider", _boom)

        deps = build_deps(_settings(), _reranker_settings(enabled=True))

        # Reranker недоступен, но оператор его включал.
        assert deps.reranker_provider is None
        assert deps.rerank_documents is None
        assert deps.reranker_metrics is None
        assert deps.reranker_enabled is False
        assert deps.reranker_configured is True

    def test_build_failure_keeps_embeddings(self, monkeypatch) -> None:
        monkeypatch.setattr(bootstrap, "build_reranker_provider", _boom)

        deps = build_deps(_settings(), _reranker_settings(enabled=True))

        assert deps.provider is not None
        assert deps.embed_documents is not None
        assert deps.embed_query is not None
        assert deps.embed_queries is not None
        assert deps.warmup is not None
        assert deps.describe is not None
        assert deps.metrics is not None

    async def test_build_failure_health_not_serving(self, monkeypatch) -> None:
        monkeypatch.setattr(bootstrap, "build_reranker_provider", _boom)
        deps = build_deps(_settings(), _reranker_settings(enabled=True))
        health = _FakeHealth()
        ready = {"value": False}

        servicer = await main._prepare_reranker(deps, health, ready)

        # Servicer регистрируется (→ Rerank = UNAVAILABLE, не UNIMPLEMENTED),
        # но готовности нет и health отдаёт NOT_SERVING.
        assert servicer is not None
        assert ready["value"] is False
        assert health.statuses == [(_RERANKER_SERVICE, NOT_SERVING)]
