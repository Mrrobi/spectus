.PHONY: install dev test test-fast lint format typecheck migrate demo notebook clean

install:
	uv sync --extra dev --extra notebook
	uv run playwright install chromium

migrate:
	uv run alembic upgrade head

dev: migrate
	uv run uvicorn app.main:app --reload --port 8000

notebook: migrate
	uv run jupyter lab notebooks/personal.ipynb

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
