.PHONY: install dev test lint typecheck migrate demo clean notebook docker docker-run docker-up docker-down

install:
	uv sync --extra dev --extra notebook
	uv run playwright install chromium

notebook: migrate
	uv run jupyter lab notebooks/personal.ipynb

migrate:
	uv run alembic upgrade head

dev: migrate
	uv run uvicorn app.main:app --reload --port 8000

demo: migrate
	uv run python scripts/seed_demo.py
	uv run python scripts/run_demo_extraction.py

test:
	uv run pytest -n auto --cov=app

test-fast:
	uv run pytest -n auto -m "not browser"

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy app

clean:
	rm -rf artifacts/ metrics.json spectus.db spectus.db-* .pytest_cache .mypy_cache .ruff_cache

docker:
	docker build -t spectus:latest .

docker-run: docker
	docker run --rm -p 8000:8000 --env-file .env -v spectus-data:/data spectus:latest

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
