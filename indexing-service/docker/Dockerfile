# syntax=docker/dockerfile:1
# Multi-stage: uv-build -> slim runtime. Один образ на роли consumer/cli.
# По умолчанию БЕЗ extra "embedding" (torch/BGE-M3) — образ слим; для
# продакшена собирайте с `--build-arg INSTALL_EMBEDDING=1` и запускайте
# в режиме INDEXING_EMBEDDING_MODE=local.
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app
# Сначала зависимости (кешируемый слой), потом код.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=builder --chown=app:app /app /app
COPY --chown=app:app docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER app
ENTRYPOINT ["/entrypoint.sh"]
CMD ["faststream", "run", "indexing_service.presentation.messaging.consumer_app:app", "--workers", "1"]
