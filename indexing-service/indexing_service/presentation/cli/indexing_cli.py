"""Typer CLI — операции индексации (§8, §9, §12)."""

import asyncio

import typer

from indexing_service.bootstrap import build_batch
from indexing_service.infrastructure.config import get_settings

app = typer.Typer(
    help="indexing-service — операции индексации", no_args_is_help=True
)


@app.command()
def provision() -> None:
    """Создать коллекцию Qdrant и направить на неё alias."""
    asyncio.run(_provision())


@app.command()
def reconcile() -> None:
    """Сверить каталог с Qdrant и починить дрейф (§9)."""
    asyncio.run(_reconcile())


@app.command()
def reindex(
    target: str = typer.Option(..., help="имя новой коллекции"),
) -> None:
    """Полная переиндексация в новую коллекцию + свап alias (§8)."""
    asyncio.run(_reindex(target))


async def _provision() -> None:
    deps = await build_batch(get_settings())
    try:
        await deps.provisioner.ensure()
        await deps.provisioner.point_alias(deps.alias)
        typer.echo("коллекция и alias готовы")
    finally:
        await deps.aclose()


async def _reconcile() -> None:
    deps = await build_batch(get_settings())
    try:
        typer.echo(str(await deps.reconcile.execute()))
    finally:
        await deps.aclose()


async def _reindex(target: str) -> None:
    deps = await build_batch(get_settings())
    try:
        report = await deps.reindex.execute(
            target_collection=target, alias=deps.alias
        )
        typer.echo(str(report))
    finally:
        await deps.aclose()
