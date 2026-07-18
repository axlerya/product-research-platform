#!/bin/sh
# Ждёт Postgres, накатывает миграции, затем запускает переданную команду.
set -e

echo "[entrypoint] ожидание Postgres..."
python - <<'PY'
import asyncio
import os
import sys

import asyncpg

dsn = os.environ["CATALOG_DATABASE_URL"].replace("+asyncpg", "")


async def wait() -> None:
    for _ in range(60):
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            return
        except Exception:  # noqa: BLE001
            await asyncio.sleep(1)
    sys.exit("[entrypoint] Postgres недоступен")


asyncio.run(wait())
PY

echo "[entrypoint] применение миграций Alembic..."
alembic upgrade head

echo "[entrypoint] запуск: $*"
exec "$@"
