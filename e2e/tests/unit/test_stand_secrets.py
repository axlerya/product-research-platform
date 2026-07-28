"""Контроль того, что секреты стенда не лежат в репозитории.

Пароли и ключи обязаны приходить из ``.env`` (он под gitignore), а в
compose-файлах и init-скрипте оставаться только подстановками. Тест не требует
поднятого стенда — это защита от возврата литералов в коммит.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

_ROOT = Path(__file__).resolve().parents[3]
_COMPOSE_FILES = ("docker-compose.yml", "docker-compose.cpu.yml")
_INIT_SCRIPT = _ROOT / "docker" / "postgres" / "init-databases.sh"
_ENV_EXAMPLE = _ROOT / ".env.example"

# Значение ключа, в имени которого есть PASSWORD / PASS / API_KEY.
_SECRET_ASSIGNMENT = re.compile(
    r"^\s*[\w.]*(?:PASSWORD|PASS|API_KEY)\w*:\s*(?P<value>\S+)",
    re.IGNORECASE | re.MULTILINE,
)
# Пароль внутри DSN вида scheme://user:secret@host.
_DSN_SECRET = re.compile(r"://[^:/@\s]+:(?P<secret>[^@\s]+)@")
# Ссылка на переменную окружения.
_REFERENCE = re.compile(r"\$\{(?P<name>[A-Z_][A-Z0-9_]*)")


def _read(name: str) -> str:
    """Файл без строк-комментариев: в них разбирать нечего.

    Комментарии объясняют требуемую форму записи и содержат её примеры —
    без отсева они выглядели бы как настоящие ссылки и значения.
    """
    text = (_ROOT / name).read_text(encoding="utf-8")
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


@pytest.mark.parametrize("name", _COMPOSE_FILES)
def test_secret_values_are_interpolated(name: str) -> None:
    """Значение любого «парольного» ключа — подстановка, а не литерал."""
    literals = [
        match.group("value")
        for match in _SECRET_ASSIGNMENT.finditer(_read(name))
        if not match.group("value").startswith("${")
    ]

    assert literals == []


@pytest.mark.parametrize("name", _COMPOSE_FILES)
def test_dsn_passwords_are_interpolated(name: str) -> None:
    """В строках подключения пароль тоже подставляется из окружения."""
    literals = [
        match.group("secret")
        for match in _DSN_SECRET.finditer(_read(name))
        if not match.group("secret").startswith("${")
    ]

    assert literals == []


def test_init_script_does_not_embed_passwords() -> None:
    """Init-скрипт получает пароли из окружения, а не из текста."""
    script = _INIT_SCRIPT.read_text(encoding="utf-8")

    assert "PASSWORD :'password'" in script
    assert re.search(r"PASSWORD\s+'", script) is None


def test_every_referenced_variable_is_documented() -> None:
    """Каждая требуемая переменная описана в .env.example.

    Иначе стенд падает на ``${VAR:?...}``, а человеку негде посмотреть, что
    именно от него хотят.
    """
    example = _ENV_EXAMPLE.read_text(encoding="utf-8")
    declared = {
        line.split("=", 1)[0].strip()
        for line in example.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    referenced = {
        match.group("name")
        for name in _COMPOSE_FILES
        for match in _REFERENCE.finditer(_read(name))
    }

    assert referenced <= declared
