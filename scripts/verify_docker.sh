#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

cleanup() {
  docker compose down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Building the application image..."
docker compose build

echo "Starting the application..."
docker compose up -d

container_id="$(docker compose ps -q receipt-ai)"
if [ -z "$container_id" ]; then
  echo "Container did not start" >&2
  docker compose logs receipt-ai >&2
  exit 1
fi

echo "Waiting for the container health check..."
for _ in $(seq 1 60); do
  status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "$container_id")"
  if [ "$status" = "healthy" ]; then
    break
  fi
  if [ "$status" = "unhealthy" ]; then
    echo "Container became unhealthy" >&2
    docker compose logs receipt-ai >&2
    exit 1
  fi
  sleep 2
done

if [ "$(docker inspect --format '{{.State.Health.Status}}' "$container_id")" != "healthy" ]; then
  echo "Timed out waiting for health" >&2
  docker compose logs receipt-ai >&2
  exit 1
fi

echo "Checking HTTP health endpoints..."
curl -fsS http://127.0.0.1:8000/healthz >/dev/null
curl -fsS http://127.0.0.1:8000/readyz >/dev/null
curl -fsS http://127.0.0.1:8000/ >/dev/null
curl -fsS http://127.0.0.1:8000/api/tools >/dev/null

echo "Checking database files are inside the mounted volume..."
docker compose exec -T receipt-ai test -f /app/data/receipts.db
docker compose exec -T receipt-ai test -f /app/data/vectors.db

echo "Writing a persistence marker..."
docker compose exec -T receipt-ai sh -c 'echo persistence-ok > /app/data/persistence_check.txt'

echo "Restarting the container..."
docker compose restart receipt-ai
container_id="$(docker compose ps -q receipt-ai)"
for _ in $(seq 1 60); do
  status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "$container_id")"
  if [ "$status" = "healthy" ]; then
    break
  fi
  sleep 2
done
docker compose exec -T receipt-ai sh -c 'test "$(cat /app/data/persistence_check.txt)" = "persistence-ok"'
docker compose exec -T receipt-ai rm -f /app/data/persistence_check.txt

echo "Docker smoke test passed: health checks, volume persistence, and HTTP routes are working."
