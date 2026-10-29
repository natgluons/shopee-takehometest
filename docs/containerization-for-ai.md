# Containerization for AI workloads

## Why containers fit AI systems

AI applications combine fragile pieces: Python versions, native libraries, OCR engines, model
runtimes, GPU drivers, and large assets. A container image captures the operating system packages
and the application environment in one immutable artifact. The same artifact can run on a laptop,
in CI, and in production.

For this project the container must satisfy more than "Python runs". It needs Tesseract and its
language data, Pillow build dependencies, a writable data directory, and a non-root runtime. Baking
those into the image removes setup drift.

## What to containerize

| Component | Container guidance |
| --- | --- |
| Web application | One image, non-root, health check, read-only root where possible |
| OCR engine | Install as a system package in the same image or a dedicated worker image |
| Vector store | SQLite is embedded. A dedicated service (Qdrant, pgvector) would be its own image |
| Model weights | Mount a cache volume or pull at startup. Do not rebuild the image for each model |
| Training jobs | Separate job image, checkpoint volume, GPU resource requests |
| Batch OCR | Worker image that consumes a queue, scaled independently of the API |

## Runtime design for this repository

- Multi-stage Dockerfile. The builder installs build dependencies and builds a wheel. The runtime
  stage installs only the wheel, Tesseract, and runtime libraries.
- Non-root user. The image creates an unprivileged user and gives it ownership of `/app/data`.
- Persistent volume. `docker-compose.yml` mounts a named volume at `/app/data` so receipts, the
  SQLite database, and the vector database survive restarts.
- Health check. `/healthz` proves the process is alive and `/readyz` proves the database is
  reachable.
- Configuration by environment. Paths, upload limits, OCR language, and optional LLM credentials are
  injected at runtime, never baked into the image.
- No dataset in the image. `.dockerignore` excludes the large customer files, tests caches, and git
  history.

## Local workflow

```bash
docker build -t receipt-ai:local .
docker compose up --build
curl -fsS http://localhost:8000/healthz
```

The upload and query flows are available at <http://localhost:8000>. Stopping and recreating the
container keeps the named volume, which is verified by the persistence smoke test.

## Production considerations

- Keep images small. Use slim base images, clean package lists, and avoid dev dependencies.
- Pin base image digests and dependency versions for reproducibility.
- Scan images for vulnerabilities in CI.
- Run as non-root and set a read-only root filesystem with an explicit writable data mount.
- Set CPU and memory limits. OCR and image decoding are memory hotspots.
- Separate liveness from readiness. A process can be alive while the database is unavailable.
- Push secrets through a secret manager or runtime environment, not image layers.
- Publish immutable tags plus a moving tag. Tag by commit SHA and optionally by semantic version.
- For GPU training, do not treat a container as a scheduler. Use Kubernetes jobs, Ray, or a managed
  training service, and checkpoint to durable storage.

## When not to use a container

Containers add overhead for a one-off notebook or a quick local experiment. They are also a poor fit
for workloads that need host-level devices without a proper runtime integration. Training large
models usually benefits more from a scheduler and distributed storage than from a single Docker
image.
