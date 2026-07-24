"""Дымовой тест каркаса: слои Clean Architecture импортируются как пакеты."""

import importlib

import pytest

LAYERS = [
    "research_agent_service",
    "research_agent_service.domain",
    "research_agent_service.application",
    "research_agent_service.infrastructure",
    "research_agent_service.presentation",
]


@pytest.mark.parametrize("module_name", LAYERS)
def test_layer_package_importable(module_name: str) -> None:
    """Каждый слой импортируется и является пакетом (есть __path__)."""
    module = importlib.import_module(module_name)

    assert hasattr(module, "__path__"), f"{module_name} должен быть пакетом"
