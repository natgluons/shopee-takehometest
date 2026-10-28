.PHONY: install lint format format-check test cov run analyze stream benchmark demo docker-build docker-up docker-down fresh-check

install:
	python3 -m pip install -e ".[dev,analysis]"

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format --check .

test:
	pytest

cov:
	pytest --cov=receipt_ai --cov-report=term-missing

run:
	uvicorn receipt_ai.api.main:app --host 0.0.0.0 --port 8000 --reload

analyze:
	python3 -m receipt_ai.csv_analysis.cli --input customers-100000.csv --outdir reports

stream:
	python3 -m receipt_ai.streaming.cli --input customers-2000000.csv --batch-size 5000

benchmark:
	python3 -m receipt_ai.streaming.cli --input customers-2000000.csv --benchmark

demo:
	bash scripts/demo.sh

docker-build:
	docker build -t receipt-ai:local .

docker-up:
	docker compose up --build

docker-down:
	docker compose down

fresh-check:
	bash scripts/fresh_clone_check.sh
