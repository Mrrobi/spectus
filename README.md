# spectus

AI-assisted web data extractor. Paste a URL, describe what you want in plain English, get structured JSON or CSV. Resilient to DOM changes — falls back to semantic LLM extraction over a facts bundle (structured data + visible text + anchors + label-value pairs) when CSS selectors fail.

```
$ spectus extract https://news.ycombinator.com/ "Extract top stories: title, points, author, comments_count, story_url" --output csv
title,points,author,comments_count,story_url
Mercurial, 20 years and counting,70,ibobev,3,https://fosdem.org/...
...
```

---

## Install — pick one

### 1. Docker (any OS)

```
docker compose up -d --build
```

Server on `http://localhost:8000`. Volume `spectus-data` persists DB + artifacts.

One-shot extract via the image:

```
docker run --rm --env-file .env -v spectus-data:/data spectus:latest \
    spectus extract https://example.com/products "extract title, price, link"
```

### 2. pip / uv (Python 3.12+ on Win/Linux/Mac)

```
pip install spectus                   # or:  uv tool install spectus
spectus install-browsers              # one-time playwright chromium download
spectus migrate                       # apply DB migrations
export OPENAI_API_KEY=sk-...          # Windows:  setx OPENAI_API_KEY sk-...
spectus serve                         # API on :8000
```

Or one-shot from the shell, no server:

```
spectus extract https://example.com "Extract titles and prices" --output csv > out.csv
```

### 3. From source

```
git clone <repo>
cd spectus
uv sync --extra dev --extra notebook
uv run playwright install chromium
uv run alembic upgrade head
cp .env.example .env                  # add your OPENAI_API_KEY
uv run spectus serve
```

---

## Use in your codebase

### Python — one-shot

```python
from spectus import extract

result = extract(
    url="https://example.com/products",
    instruction="Extract each product: name, price, rating, link",
    openai_api_key="sk-...",          # optional; falls back to OPENAI_API_KEY env
    max_records=50,
)
print(result["records"])              # list[dict]
print(result["diagnostics"])          # strategy, quality_score, tokens, ...
```

### Python — reusable client (batched, faster)

```python
from spectus import SyncClient

with SyncClient.open(openai_api_key="sk-...") as client:
    r1 = client.extract(url1, "extract X, Y, Z")
    r2 = client.extract(url2, "another instruction")
```

### Python — async (FastAPI / aiohttp / asyncio)

```python
from spectus import Client

client = await Client.create(openai_api_key="sk-...")
result = await client.extract(url, instruction)
await client.close()
```

### Any language — HTTP API

```
curl -s http://localhost:8000/api/extractions \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com","instruction":"extract titles and prices"}' \
  | jq '.records'
```

### Jupyter notebook

```
make notebook        # opens notebooks/personal.ipynb in JupyterLab
```

---

## CLI reference

```
spectus serve [--host H] [--port P] [--reload]
spectus extract URL "instruction" [--browser auto|force|never] [--max-records N] [--output table|json|csv]
spectus templates [--status candidate|active|needs_review|deprecated] [--output table|json]
spectus migrate
spectus install-browsers
spectus version
```

---

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/extractions` | Run extraction (sync, deadline from settings) |
| `GET`  | `/api/extractions/{id}` | Fetch prior result |
| `GET`  | `/api/extractions/{id}/export.csv` | CSV download |
| `GET`  | `/api/templates` | List saved templates |
| `GET`  | `/api/templates/{id}` | Get specific template |
| `GET`  | `/health` | Liveness probe |
| `GET`  | `/metrics` | Counters + p50/p95/p99 histograms |

OpenAPI spec at `/docs` (Swagger UI) and `/redoc`.

### Request

```json
{
  "url": "https://example.com/products",
  "instruction": "Extract title, price, rating, and product URL",
  "output_format": "json",
  "options": {
    "use_browser": "auto",
    "max_records": 100,
    "save_template": true
  }
}
```

### Response

```json
{
  "job_id": "...",
  "status": "success",
  "url": "...",
  "instruction": "...",
  "records": [...],
  "diagnostics": {
    "strategy_used": "semantic_extraction",
    "page_type": "product_listing",
    "static_or_browser": "static",
    "records_found": 24,
    "quality_score": 0.87,
    "repair_attempts": 1,
    "template_used": false,
    "runtime_ms": 13125,
    "llm_calls": 3,
    "llm_tokens_in": 4865,
    "llm_tokens_out": 749,
    "warnings": []
  }
}
```

---

## Architecture

```
POST /api/extractions
  -> URL normalize + SSRF + robots + rate-limit  (≤ 200 ms)
  -> parallel(intent_LLM, static_fetch + analyze)
  -> template lookup → on hit, execute + validate → return  (<1s warm path)
  -> static-sufficient? → planner_LLM → executor → validator
                       else browser_render → re-analyze → planner → executor → validator
  -> repair loop (≤2) if quality_score < 0.80
  -> resilience pass: build facts bundle → semantic LLM extraction →
                       per-field merge with type-aware tie-breakers
  -> save winning strategy as template (candidate → active after 3 successes)
  -> return JSON or CSV with diagnostics
```

Seven extraction strategies:
- `structured_data` — JSON-LD / OpenGraph / `__NEXT_DATA__` / `__NUXT__`
- `single_dom_selector` — page-level CSS
- `repeated_dom_selector` — repeating container CSS
- `table_extraction` — HTML tables
- `article_extraction` — trafilatura
- `visible_text_regex` — regex over visible text
- `semantic_extraction` — LLM reads facts bundle (text + anchors + labels), no DOM dependency — survives redesigns

Stack: Python 3.12 · FastAPI · Pydantic v2 (strict) · SQLAlchemy 2.0 async · SQLite (swap to Postgres via `DB_URL`) · selectolax · Playwright · OpenAI Structured Outputs · structlog · trafilatura.

---

## Configuration

All settings in `.env` (see `.env.example`). Key vars:

| Var | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | Required (or pass via `openai_api_key=` kwarg) |
| `OPENAI_MODEL_INTENT` | `gpt-4o-mini` | Intent parser model |
| `OPENAI_MODEL_PLAN` | `gpt-4.1` | Planner + repair + semantic model |
| `DB_URL` | `sqlite+aiosqlite:///./spectus.db` | Swap to `postgresql+asyncpg://...` for Postgres |
| `ARTIFACTS_DIR` | `./artifacts` | Per-job debug bundles |
| `BROWSER_POOL_SIZE` | `3` | Playwright contexts |
| `RATE_LIMIT_RPS` | `1.0` | Per-domain token-bucket refill |
| `ALLOW_PRIVATE_TARGETS` | `false` | Set `true` only for local fixture testing |
| `JOB_DEADLINE_SEC` | `180` | Hard wall-time per request |

GPT-5 / o-series support: pass `OPENAI_MODEL_*=gpt-5-nano` and bump `LLM_*_TIMEOUT_SEC` (reasoning tokens take longer). Client auto-uses `max_completion_tokens` + `reasoning_effort=low` for those models.

---

## Compliance + safety (built-in)

- SSRF: blocks private / loopback / link-local / reserved IPs before fetch.
- Robots.txt: 1h-TTL cache, fail-open on 5xx.
- Per-domain rate-limit token bucket.
- Allowed selector attributes: `text`, `href`, `src`, `alt`, `title`, `class`, `id`, `value`, `data-*`, `aria-*`. Anything else rejected at Pydantic boundary.
- jQuery extensions (`:has()`, `:is()`, `:visible`, etc.) rejected before reaching the parser. `:contains('text')` is translated server-side (lexbor CSS + text filter).
- No CAPTCHA solve, no auth bypass, no anti-bot evasion. Out of scope by design.

---

## Development

```
make dev          # uvicorn --reload on :8000
make test         # pytest -n auto with coverage
make lint         # ruff
make typecheck    # mypy strict
```

Suite: 52 unit tests, runs <1s offline. Plus `@pytest.mark.browser` for real Chromium.

---

## License

MIT.
