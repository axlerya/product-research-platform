#!/usr/bin/env sh
# Генерация Python-стабов из proto. Запускать из корня research-agent-service:
#   sh contracts/proto/generate.sh
# Требует dev-зависимость grpcio-tools (uv sync).
set -eu

OUT=research_agent_service/infrastructure/grpc/_generated

uv run python -m grpc_tools.protoc \
  -I contracts/proto/embedding/v1 \
  --python_out="$OUT" \
  --grpc_python_out="$OUT" \
  --pyi_out="$OUT" \
  embedding.proto

uv run python -m grpc_tools.protoc \
  -I contracts/proto/reranker/v1 \
  --python_out="$OUT" \
  --grpc_python_out="$OUT" \
  --pyi_out="$OUT" \
  reranker.proto

# grpc-стабы импортируют pb2 как top-level модуль — правим на относительный.
uv run python - <<'PY'
import io

for name in ("embedding", "reranker"):
    path = f"research_agent_service/infrastructure/grpc/_generated/{name}_pb2_grpc.py"
    text = io.open(path, encoding="utf-8").read()
    text = text.replace(
        f"import {name}_pb2 as", f"from . import {name}_pb2 as"
    )
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)
print("stubs generated + imports fixed")
PY
