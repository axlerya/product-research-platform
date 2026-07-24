#!/bin/sh
# Ждёт Postgres, при RUN_MIGRATIONS=1 накатывает миграции, запускает команду.
# Redis/RabbitMQ/Qdrant и внешние сервисы дожидаются на уровне рантайма
# (readiness /ready и reconnect клиентов), поэтому здесь их нет.
#
# Миграции накатывает только роль с RUN_MIGRATIONS=1 — иначе несколько
# процессов полезли бы в alembic одновременно.
set -e

echo "[entrypoint] ожидание Postgres..."
python - <<'PY'
import asyncio
import sys
import time

import asyncpg

from research_agent_service.infrastructure.config import get_settings


async def probe(dsn: str) -> bool:
    try:
        conn = await asyncpg.connect(dsn, timeout=2)
    except Exception:
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
