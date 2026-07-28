# syntax=docker/dockerfile:1
# Контейнер детерминированных тестовых провайдеров стенда (LLM + web-поиск).
# Тестовые зависимости в образ не попадают: он несёт только ASGI-обвязку.
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY doubles ./doubles
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
CMD ["uvicorn", "doubles.app:app", "--host", "0.0.0.0", "--port", "8000"]
