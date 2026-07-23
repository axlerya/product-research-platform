# syntax=docker/dockerfile:1
# Multi-stage: uv-build -> slim runtime. Один образ на все роли:
# consumer / result-consumer / relay / cli. Модели и torch внутри нет —
# векторы считает embedding-service, мы только заказываем их командой.
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
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "indexing_service.presentation.messaging.consumer_app:app", "--host", "0.0.0.0", "--port", "8000"]
