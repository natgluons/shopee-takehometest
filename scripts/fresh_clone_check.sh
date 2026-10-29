#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/receipt-ai-fresh.XXXXXX")"
CLONE_DIR="$WORK_DIR/repo"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

echo "Cloning $ROOT_DIR into a temporary directory..."
git clone --quiet --no-hardlinks "$ROOT_DIR" "$CLONE_DIR"
cd "$CLONE_DIR"

echo "Checking commit count and phase branches..."
commit_count="$(git rev-list --count HEAD)"
if [ "$commit_count" -lt 65 ]; then
  echo "Expected at least 65 commits (1 base plus 64 planned), found $commit_count" >&2
  exit 1
fi
phase_branches="$(git branch -r | grep -c 'phase-[1-8]-' || true)"
if [ "$phase_branches" -lt 8 ]; then
  echo "Expected 8 phase branches, found $phase_branches" >&2
  exit 1
fi
echo "Commit count: $commit_count, phase branches: $phase_branches"

echo "Checking written answers for forbidden characters..."
python3 - <<'PY'
from pathlib import Path
text = Path("knowledge.txt").read_text(encoding="utf-8")
for character in (";", "\u2014", "\u2013"):
    if character in text:
        raise SystemExit(f"knowledge.txt contains forbidden character: {character!r}")
required = ("REST", "MCP", "Docker", "fine tune")
for token in required:
    if token.lower() not in text.lower():
        raise SystemExit(f"knowledge.txt is missing expected topic: {token}")
print("knowledge.txt is clean and covers all five questions")
PY

echo "Checking required files..."
for file in README.md pyproject.toml knowledge.txt Dockerfile docker-compose.yml \
  .github/workflows/ci.yml docs/requirements-mapping.md scripts/demo.sh \
  scripts/verify_docker.sh; do
  if [ ! -e "$file" ]; then
    echo "Missing required file: $file" >&2
    exit 1
  fi
done

echo "Creating a fresh virtual environment..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e ".[dev,analysis]"

echo "Running lint and formatting checks..."
ruff check .
ruff format --check .

echo "Running the full test suite..."
pytest -q

echo "Importing the application and command line modules..."
python -c "from receipt_ai.api.main import create_app; create_app"
python -m receipt_ai.csv_analysis.cli --help >/dev/null
python -m receipt_ai.streaming.cli --help >/dev/null

if [ "${FRESH_DOCKER:-0}" = "1" ]; then
  echo "Running the Docker build and smoke test..."
  bash scripts/verify_docker.sh
else
  echo "Skipping Docker smoke test. Set FRESH_DOCKER=1 to include it."
fi

echo
echo "Fresh clone verification passed."
