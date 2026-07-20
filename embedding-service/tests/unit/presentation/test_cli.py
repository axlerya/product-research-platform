"""Unit-тесты Typer CLI (deterministic-режим, без модели/GPU)."""

from collections.abc import Iterator

import pytest
from typer.testing import CliRunner

from embedding_service.infrastructure.config import get_settings
from embedding_service.presentation.cli.embedding_cli import app


@pytest.fixture
def deterministic_env(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    monkeypatch.setenv("EMBEDDING_PROVIDER_MODE", "deterministic")
    monkeypatch.setenv("EMBEDDING_DIM", "8")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_describe_model(deterministic_env: None) -> None:
    result = CliRunner().invoke(app, ["describe-model"])
    assert result.exit_code == 0, result.output
    assert (
        "model_version=BAAI/bge-m3@unknown|pool=cls|norm=1|dim=8"
        in result.stdout
    )


def test_warmup(deterministic_env: None) -> None:
    result = CliRunner().invoke(app, ["warmup"])
    assert result.exit_code == 0, result.output
    assert "ready model_version=" in result.stdout
