#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
USE_DOCKER="${DEMO_USE_DOCKER:-1}"

# The demo is deterministic by default. Set DEMO_LLM=1 to exercise a configured model.
if [ "${DEMO_LLM:-0}" != "1" ]; then
  export OPENAI_API_KEY=""
fi

if [ "$USE_DOCKER" = "1" ]; then
  echo "Starting the application with Docker Compose..."
  docker compose up -d --build
else
  echo "DEMO_USE_DOCKER=0, expecting an application already running at $BASE_URL"
fi

echo "Waiting for $BASE_URL/healthz ..."
for _ in $(seq 1 60); do
  if curl -fsS "$BASE_URL/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! curl -fsS "$BASE_URL/healthz" >/dev/null 2>&1; then
  echo "Application did not become healthy. Start it with: uvicorn receipt_ai.api.main:app" >&2
  exit 1
fi

BASE_URL="$BASE_URL" python3 scripts/demo_client.py

echo
echo "Demo complete. The application is still running at $BASE_URL."
echo "Stop it with: docker compose down"
