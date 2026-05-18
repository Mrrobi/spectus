FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY app/ ./app/
COPY notebooks/ ./notebooks/
COPY alembic/ ./alembic/
COPY alembic.ini ./

RUN uv sync --frozen --no-dev
RUN uv run playwright install --with-deps chromium

ENV PATH="/app/.venv/bin:${PATH}" \
    ARTIFACTS_DIR=/data/artifacts \
    DB_URL=sqlite+aiosqlite:////data/spectus.db \
    METRICS_PATH=/data/metrics.json \
    BROWSER_POOL_SIZE=3 \
    BROWSER_HEADLESS=true \
    LOG_LEVEL=INFO

RUN mkdir -p /data /data/artifacts && chmod 777 /data /data/artifacts

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -fs http://127.0.0.1:8000/health || exit 1

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
