"""Контракт с рантаймом моделей: границы версий тяжёлых зависимостей.

FlagEmbedding зовёт у токенайзера ``prepare_for_model`` — метод, которого в
transformers 5.x уже нет. Без верхней границы резолвер берёт 5.x: эмбеддинги
при этом ещё работают, а прогрев reranker падает, и реранкинг молча
деградирует на каждом запросе. Проверяем и объявление, и то, что реально
зафиксировано в lock-файле.
"""

import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

_ROOT = Path(__file__).resolve().parents[2]
_MAX_TRANSFORMERS_MAJOR = 5


def _extras() -> dict[str, list[str]]:
    manifest = tomllib.loads(
        (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    return manifest["project"]["optional-dependencies"]


@pytest.mark.parametrize("extra", ["embedding", "reranking"])
def test_transformers_is_capped_below_five(extra: str) -> None:
    """Оба extra объявляют верхнюю границу transformers."""
    requirements = [
        item for item in _extras()[extra] if item.startswith("transformers")
    ]

    assert requirements, f"extra {extra} не объявляет transformers"
    assert "<5" in requirements[0]


def test_locked_transformers_respects_the_cap() -> None:
    """В lock-файле зафиксирована совместимая с FlagEmbedding версия."""
    lock = tomllib.loads((_ROOT / "uv.lock").read_text(encoding="utf-8"))
    versions = [
        package["version"]
        for package in lock["package"]
        if package["name"] == "transformers"
    ]

    assert versions, "transformers отсутствует в uv.lock"
    for version in versions:
        assert int(version.split(".")[0]) < _MAX_TRANSFORMERS_MAJOR
