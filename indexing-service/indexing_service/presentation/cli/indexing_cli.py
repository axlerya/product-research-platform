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
    """Завести эпоху переиндексации в новую коллекцию (§8).

    Только ставит задания: векторы считает embedding-service. Переключить
    alias — отдельной командой ``reindex-swap``, когда эпоха будет готова.
    """
    asyncio.run(_reindex(target))


@app.command(name="reindex-swap")
def reindex_swap(
    target: str = typer.Option(..., help="имя новой коллекции"),
    min_ready: float = typer.Option(
        1.0, help="требуемая доля завершённых заданий (1.0 — все)"
    ),
) -> None:
    """Переключить alias на новую коллекцию, если эпоха готова (Q6)."""
    asyncio.run(_reindex_swap(target, min_ready))


@app.command(name="replay-dlq")
def replay_dlq() -> None:
    """Переотправить запаркованные (DLQ) сообщения в основной exchange."""
    asyncio.run(_replay_dlq())


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
        # Вторая сторона сверки: команды, на которые не пришёл ответ.
        typer.echo(str(await deps.reconcile_jobs.execute()))
    finally:
        await deps.aclose()


async def _reindex(target: str) -> None:
    deps = await build_batch(get_settings())
    try:
        report = await deps.reindex.execute(target_collection=target)
        typer.echo(str(report))
        typer.echo(
            "задания поставлены; alias переключить командой reindex-swap"
        )
    finally:
        await deps.aclose()


async def _reindex_swap(target: str, min_ready: float) -> None:
    deps = await build_batch(get_settings())
    try:
        report = await deps.reindex.swap(
            target_collection=target,
            alias=deps.alias,
            min_ready=min_ready,
        )
        typer.echo(str(report))
        if not report.swapped:
            typer.echo("эпоха ещё не готова — alias не переключён")
            raise typer.Exit(code=1)
    finally:
        await deps.aclose()


async def _replay_dlq() -> None:
    from faststream.rabbit import RabbitBroker

    from indexing_service.presentation.messaging.dlq import replay_parked

    broker = RabbitBroker(get_settings().rabbitmq_dsn)
    async with broker:
        count = await replay_parked(broker)
    typer.echo(f"переотправлено: {count}")
