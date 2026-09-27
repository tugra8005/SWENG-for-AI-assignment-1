#!/usr/bin/env bash
# Docker'sız yerel geliştirme yığını: üç defter düğümü + API (bellek içi graf).
# PostgreSQL'in DATABASE_URL ile erişilebilir olması gerekir. Asıl kurulum: docker compose up.
#
#   DATABASE_URL=postgresql+psycopg://user:pass@127.0.0.1:5432/mesveret_dev scripts/dev_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."
: "${DATABASE_URL:?DATABASE_URL verilmeli}"
DATA="${LEDGER_DATA_ROOT:-$PWD/.local-ledger}"
TOKEN=dev-ledger-token
pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT

start_node() {
  local id=$1 port=$2 role=$3
  mkdir -p "$DATA/$id"
  (cd ledger && NODE_ID=$id ROLE=$role DATA_DIR="$DATA/$id" LEDGER_TOKEN=$TOKEN \
    FOLLOWER_URLS=${4:-} LEADER_URL=${5:-} \
    uv run uvicorn --factory ledger.app:app_from_env --host 127.0.0.1 --port "$port" \
    --log-level warning) &
  pids+=($!)
}
start_node ledger-1 8101 leader "http://127.0.0.1:8102,http://127.0.0.1:8103"
start_node ledger-2 8102 follower "" "http://127.0.0.1:8101"
start_node ledger-3 8103 follower "" "http://127.0.0.1:8101"
sleep 2

cd api
ENV=dev GRAPH_BACKEND=memory LEDGER_TOKEN=$TOKEN \
  LEDGER_LEADER_URL=http://127.0.0.1:8101 \
  LEDGER_NODE_URLS=http://127.0.0.1:8101,http://127.0.0.1:8102,http://127.0.0.1:8103 \
  uv run python -m mesveret.devserver --port "${API_PORT:-8000}"
