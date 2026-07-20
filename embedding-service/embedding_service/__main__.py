"""Точка входа модуля: ``python -m embedding_service`` → Typer CLI."""

from embedding_service.presentation.cli.embedding_cli import app

if __name__ == "__main__":  # pragma: no cover
    app()
