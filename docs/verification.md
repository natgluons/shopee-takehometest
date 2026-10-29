# Final verification

## What was verified

The final check runs from a fresh clone in a temporary directory. It confirms:

- the repository clones without missing files
- the planned commit history is present
- all eight phase branches exist
- `knowledge.txt` contains no semicolons or em dashes
- required project, CI, Docker, and documentation files exist
- a fresh virtual environment installs the project and development dependencies
- Ruff lint and format checks pass
- the full pytest suite passes
- the FastAPI app and both command line modules import

The Docker smoke test is optional in the fresh-clone script because it requires a running Docker
daemon and several minutes of build time. It was run separately and passed.

## Commands

```bash
# Fast local verification (no Docker)
bash scripts/fresh_clone_check.sh

# Include the Docker build, health check, and persistence restart
FRESH_DOCKER=1 bash scripts/fresh_clone_check.sh
```

## Evidence

| Check | Result |
| --- | --- |
| Fresh clone | passed |
| Commit count | 65 total including the pre-existing base commit |
| Phase branches | 8 |
| Ruff lint | passed |
| Ruff format check | passed |
| Pytest suite | 102 tests passed |
| App import | passed |
| Dataset CLIs import | passed |
| Docker build | passed |
| Container health and readiness | passed |
| Volume persistence after restart | passed |
| Real Tesseract OCR in container | passed on a generated 900x500 receipt image |

## Dataset-dependent checks

The customer CSV files are excluded from git by design. The fresh-clone check does not run the
dataset commands because the files are not present. To reproduce the dataset results, place
`customers-100000.csv` and `customers-2000000.csv` in the repository root after cloning and run:

```bash
make analyze
make stream
make benchmark
```

The recorded results are in `docs/csv-insights.md` and `docs/benchmark-results.md`.

## Branch and commit hygiene

Each phase has a dedicated branch and was merged into `master` with a fast-forward merge, keeping a
linear history. Commit timestamps are separated by the required random intervals. The complete list
is recorded in `docs/requirements-mapping.md` and can be inspected with:

```bash
git log --oneline --decorate --all
git log --format='%h %ad %s' --date=iso
```
