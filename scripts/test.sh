#!/usr/bin/env bash
# Tüm testleri çalıştırır.
#   scripts/test.sh            → birim + defter + (Docker varsa) entegrasyon
#   scripts/test.sh --unit     → yalnızca Docker gerektirmeyen testler
#   scripts/test.sh --keep     → entegrasyon yığınını sonunda kapatma
set -euo pipefail
cd "$(dirname "$0")/.."

UNIT_ONLY=0
KEEP=0
for arg in "$@"; do
  case "$arg" in
    --unit) UNIT_ONLY=1 ;;
    --keep) KEEP=1 ;;
  esac
done

echo "== api: birim testleri"
(cd api && uv run pytest -q -m "not integration")

echo "== ledger: testler"
(cd ledger && uv run pytest -q)

if [[ $UNIT_ONLY -eq 1 ]]; then
  exit 0
fi

if ! docker info >/dev/null 2>&1; then
  echo "!! Docker çalışmıyor; entegrasyon testleri atlandı." >&2
  exit 0
fi

echo "== entegrasyon yığını başlatılıyor"
docker compose -f docker-compose.test.yml up -d --wait
cleanup() {
  if [[ $KEEP -eq 0 ]]; then
    docker compose -f docker-compose.test.yml down -v >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "== api: entegrasyon testleri"
(cd api && \
  ENV=test \
  DATABASE_URL="postgresql+psycopg://mesveret:mesveret@localhost:55432/mesveret_test" \
  NEO4J_URL="bolt://localhost:57687" NEO4J_PASSWORD="mesveret-test" \
  SCHEDULER_ENABLED=false \
  uv run pytest -q -m integration)
