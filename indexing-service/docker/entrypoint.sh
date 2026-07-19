#!/bin/sh
# Ждёт готовности Qdrant, затем запускает переданную команду.
# RabbitMQ дожидается сам FastStream (reconnect), поэтому здесь только Qdrant.
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

echo "[entrypoint] запуск: $*"
exec "$@"
