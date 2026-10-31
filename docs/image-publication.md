# Container image publication strategy

## Goals

- Every published image is traceable to a commit and a CI run.
- The same image digest is promoted across environments.
- Runtime configuration and secrets never live in the image.
- Consumers can verify what is inside the image.

## Tagging scheme

Use immutable and moving tags together.

| Tag | Example | Meaning |
| --- | --- | --- |
| Commit SHA | `sha-9f2c1ab` | Immutable, one per build |
| Semantic version | `v0.3.0` | Immutable release |
| Minor moving | `v0.3` | Latest patch in the minor line |
| Major moving | `v0` | Latest compatible release |
| Environment | `staging`, `prod` | Promoted by deployment tooling |
| Latest | `latest` | Convenience only, never for production pinning |

Production deployments should pin the commit SHA or a digest such as
`ghcr.io/org/receipt-ai@sha256:...`. Moving tags are for humans and local experiments.

## Registry layout

The default target is GitHub Container Registry:

```text
ghcr.io/<owner>/receipt-ai:sha-<commit>
ghcr.io/<owner>/receipt-ai:v0.3.0
ghcr.io/<owner>/receipt-ai:latest
```

Docker Hub or a private registry work the same way. Keep one registry per organization to avoid
split brain. Mirror to a second registry only if there is a concrete availability requirement.

## Build once, promote everywhere

1. CI builds the image once from a commit.
2. CI pushes the immutable SHA tag.
3. The release job adds semantic version tags to the same digest, without rebuilding.
4. Staging pulls the digest and runs integration tests.
5. Production is promoted by digest, not by rebuilding from source.

Rebuilding for each environment defeats the purpose of traceability, because the builder can produce
a different layer graph even from the same source.

## Example release workflow

```yaml
name: Publish image
on:
  push:
    tags: ["v*"]

permissions:
  contents: read
  packages: write

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=sha
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          provenance: true
          sbom: true
```

The current repository CI builds and smoke-tests the image but does not push it. Publication is a
deliberate manual or tag-triggered step so forks do not publish to the upstream registry.

## Security and supply chain

- Run as a non-root user. The image already does.
- Keep the runtime image minimal. Tesseract and its language data are the main system packages.
- Pin the base image to a digest for reproducible builds in release pipelines.
- Generate an SBOM (SPDX or CycloneDX) and provenance attestations.
- Scan for vulnerabilities in CI and fail on critical findings with a fix available.
- Never bake `.env`, API keys, datasets, or model weights into layers.
- Use a secret manager or runtime environment injection.
- Sign images with cosign and verify signatures at deploy time.
- Set `read_only: true`, drop Linux capabilities, and mount only the data volume.

## Local publication

```bash
docker build -t receipt-ai:local .
docker tag receipt-ai:local ghcr.io/<owner>/receipt-ai:sha-$(git rev-parse --short HEAD)
docker push ghcr.io/<owner>/receipt-ai:sha-$(git rev-parse --short HEAD)
```

If the app is run from Compose, point the service at the published image instead of `build`:

```yaml
services:
  receipt-ai:
    image: ghcr.io/<owner>/receipt-ai:sha-<commit>
```

## Rollback

Because every deployment is a digest, rollback is a redeploy of the previous digest. Keep at least
the last five release digests and a record of which commit and migration state each one expects.
SQLite schema changes should remain backward compatible for one release, or ship an explicit
migration step before the new image starts.

## Versioning the model and schema

The image contains code, not user data. The receipt database and vector database live in the mounted
volume. Changing the embedding model requires a re-index, so record the embedder name and dimension
with the release notes. Treat a schema migration as part of the release, not as an afterthought.
