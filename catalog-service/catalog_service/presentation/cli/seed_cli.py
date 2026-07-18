"""CLI seed: идемпотентное наполнение каталога из CSV.

Запуск: ``python -m catalog_service seed --file products_catalog_ru.csv``.
"""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from catalog_service.bootstrap import build_container

app = typer.Typer(add_completion=False, help="catalog-service CLI")


@app.callback()
def _cli() -> None:
    """catalog-service CLI (подкоманды ниже)."""


@app.command()
def seed(
    file: Annotated[
        Path,
        typer.Option(
            "--file", "-f", exists=True, readable=True, help="Путь к CSV"
        ),
    ],
    on_stale: Annotated[
        str, typer.Option("--on-stale", help="skip | overwrite")
    ] = "skip",
) -> None:
    """Наполняет каталог из CSV и печатает отчёт (exit 1 при ошибках строк)."""
    container = build_container()
    source = container.csv_row_source(file)
    report = asyncio.run(
        container.seed_catalog(source, on_stale=on_stale).execute()
    )
    typer.echo(
        f"Всего: {report.total} | создано: {report.created} | "
        f"контент: {report.content_changed} | "
        f"коммерция: {report.commercial_changed} | обе: {report.both} | "
        f"метрики: {report.metrics_only} | без изменений: {report.unchanged}"
        f" | пропущено: {report.skipped_stale} | "
        f"события: {report.events_emitted} | ошибок: {len(report.errors)}"
    )
    raise typer.Exit(code=1 if report.errors else 0)
