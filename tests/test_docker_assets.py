from __future__ import annotations

from pathlib import Path


def test_dockerfile_is_non_root_and_has_healthcheck(project_root: Path) -> None:
    dockerfile = (project_root / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.12-slim AS builder" in dockerfile
    assert "FROM python:3.12-slim AS runtime" in dockerfile
    assert "tesseract-ocr" in dockerfile
    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "uvicorn" in dockerfile


def test_compose_uses_volume_and_healthcheck(project_root: Path) -> None:
    compose = (project_root / "docker-compose.yml").read_text(encoding="utf-8")
    assert "receipt_data:/app/data" in compose
    assert "healthcheck:" in compose
    assert "receipt-ai:local" in compose
    assert "read_only: true" in compose


def test_dockerignore_excludes_large_data(project_root: Path) -> None:
    dockerignore = (project_root / ".dockerignore").read_text(encoding="utf-8")
    assert "*.csv" in dockerignore
    assert "data/" in dockerignore
    assert ".git" in dockerignore


def test_verify_docker_script_exists(project_root: Path) -> None:
    script = project_root / "scripts" / "verify_docker.sh"
    assert script.exists()
    assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")
