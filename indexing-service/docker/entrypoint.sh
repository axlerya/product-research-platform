#!/bin/sh
# Ждёт Qdrant и Postgres, накатывает миграции, запускает переданную команду.
# RabbitMQ дожидается сам FastStream (reconnect), поэтому его здесь нет.
#
# Миграции накатывает только роль с RUN_MIGRATIONS=1 — иначе несколько
# процессов полезли бы в alembic одновременно.
set -e

echo "[entrypoint] ожидание Qdrant..."
python - <<'PY'
import os
import sys
import time
import urllib.request

base = os.environ.get("INDEXING_QDRANT_URL", "http://qdrant:6333").rstrip("/")
url = base + "/readyz"

for _ in range(60):
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            if resp.status == 200:
                sys.exit(0)
    except Exception:  # noqa: BLE001
        time.sleep(1)
sys.exit("[entrypoint] Qdrant недоступен")
PY

echo "[entrypoint] ожидание Postgres..."
python - <<'PY'
import asyncio
import sys
import time

import asyncpg

from indexing_service.infrastructure.config import get_settings


async def probe(dsn: str) -> bool:
    try:
        conn = await asyncpg.connect(dsn, timeout=2)
    except Exception:  # noqa: BLE001
        return False
    await conn.close()
    return True


dsn = get_settings().database_url.replace("+asyncpg", "")
for _ in range(60):
    if asyncio.run(probe(dsn)):
        sys.exit(0)
    time.sleep(1)
sys.exit("[entrypoint] Postgres недоступен")
PY

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] alembic upgrade head..."
  alembic upgrade head
fi

echo "[entrypoint] запуск: $*"
exec "$@"
