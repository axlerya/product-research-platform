#!/usr/bin/env sh
# Генерация Python-стабов из proto. Запускать из корня embedding-service:
#   sh contracts/proto/generate.sh
# Требует dev-зависимость grpcio-tools (uv sync).
set -eu

OUT=embedding_service/infrastructure/grpc/_generated

uv run python -m grpc_tools.protoc \
  -I contracts/proto/embedding/v1 \
  --python_out="$OUT" \
  --grpc_python_out="$OUT" \
  --pyi_out="$OUT" \
  embedding.proto

# grpc-стаб импортирует pb2 как top-level модуль — правим на относительный
# импорт, чтобы пакет резолвился внутри infrastructure.grpc._generated.
uv run python - <<'PY'
import io

path = "embedding_service/infrastructure/grpc/_generated/embedding_pb2_grpc.py"
text = io.open(path, encoding="utf-8").read()
text = text.replace(
    "import embedding_pb2 as", "from . import embedding_pb2 as"
)
io.open(path, "w", encoding="utf-8", newline="\n").write(text)
print("stubs generated + import fixed")
PY

# --- reranker (изолированный пакет reranker.v1, отдельный сервис) ---
uv run python -m grpc_tools.protoc \
  -I contracts/proto/reranker/v1 \
  --python_out="$OUT" \
  --grpc_python_out="$OUT" \
  --pyi_out="$OUT" \
  reranker.proto

uv run python - <<'PY'
import io

path = "embedding_service/infrastructure/grpc/_generated/reranker_pb2_grpc.py"
text = io.open(path, encoding="utf-8").read()
text = text.replace(
    "import reranker_pb2 as", "from . import reranker_pb2 as"
)
io.open(path, "w", encoding="utf-8", newline="\n").write(text)
print("reranker stubs generated + import fixed")
PY
