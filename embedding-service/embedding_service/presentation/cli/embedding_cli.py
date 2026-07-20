"""Typer CLI embedding-service: describe-model / warmup / serve."""

import asyncio

import typer

from embedding_service.application.dto import ProviderStatus
from embedding_service.application.use_cases.describe_model import DescribeModel
from embedding_service.application.use_cases.warmup_model import WarmupModel
from embedding_service.infrastructure.config import Settings, get_settings
from embedding_service.infrastructure.embedding.factory import build_provider

app = typer.Typer(help="embedding-service CLI", add_completion=False)


@app.command("describe-model")
def describe_model() -> None:
    """Печатает статус модели (model_version / device / precision)."""
    status = asyncio.run(_describe(get_settings()))
    typer.echo(
        f"model_version={status.model_key} "
        f"device={status.device} precision={status.precision}"
    )


@app.command()
def warmup() -> None:
    """Прогревает модель и печатает готовность."""
    status = asyncio.run(_warmup(get_settings()))
    typer.echo(f"ready model_version={status.model_key}")


@app.command()
def serve() -> None:  # pragma: no cover - runtime (запуск обеих плоскостей)
    """Запускает обе транспортные плоскости (composition root)."""
    from embedding_service.main import run

    asyncio.run(run())


async def _describe(settings: Settings) -> ProviderStatus:
    provider = build_provider(settings)
    return await DescribeModel(provider).handle()


async def _warmup(settings: Settings) -> ProviderStatus:
    provider = build_provider(settings)
    try:
        return await WarmupModel(provider).handle()
    finally:
        await provider.aclose()
