# spectus

AI-assisted web data extractor. Paste a URL, describe what you want in plain English, get structured JSON or CSV. Resilient to DOM changes — falls back to semantic LLM extraction over a facts bundle (structured data + visible text + anchors + label-value pairs) when CSS selectors fail.

```
$ spectus extract https://news.ycombinator.com/ "Extract top stories: title, points, author, comments_count, story_url" --output csv
title,points,author,comments_count,story_url
Mercurial, 20 years and counting,70,ibobev,3,https://fosdem.org/...
...
```

[![PyPI](https://img.shields.io/pypi/v/spectus.svg)](https://pypi.org/project/spectus/) [![Python](https://img.shields.io/pypi/pyversions/spectus.svg)](https://pypi.org/project/spectus/) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## Install

```bash
pip install spectus                   # or:  uv tool install spectus
spectus install-browsers              # one-time playwright chromium download (~110 MB)
spectus migrate                       # apply DB migrations
export OPENAI_API_KEY=sk-...          # Windows:  setx OPENAI_API_KEY sk-...
```

Requires Python 3.12+. Works on Linux, macOS, and Windows.

---

## Use

### CLI — one-shot

```bash
spectus extract https://example.com/products "Extract title, price, rating, and product URL" --output json
spectus extract https://news.ycombinator.com/ "Top stories: title, points, author" --output csv > out.csv
```

### CLI — server mode

```bash
spectus serve                         # API on http://localhost:8000
spectus serve --host 0.0.0.0 --port 9000
```

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

```bash
spectus serve
# then:
curl -s http://localhost:8000/api/extractions \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com","instruction":"extract titles and prices"}' \
  | jq '.records'
```

### Jupyter notebook

```bash
spectus install-browsers
# clone the repo, then:
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

Seven extraction strategies, chosen automatically:

- `structured_data` — JSON-LD / OpenGraph / `__NEXT_DATA__` / `__NUXT__`
- `single_dom_selector` — page-level CSS
- `repeated_dom_selector` — repeating container CSS (lists, grids)
- `table_extraction` — HTML tables with header→field mapping
- `article_extraction` — trafilatura (clean article body + metadata)
- `visible_text_regex` — regex over visible text (fallback)
- `semantic_extraction` — LLM reads a facts bundle (text + anchors + labels + KV pairs), no DOM dependency — survives redesigns

Stack: Python 3.12 · FastAPI · Pydantic v2 (strict) · SQLAlchemy 2.0 async · SQLite (swap to Postgres via `DB_URL`) · selectolax · Playwright · OpenAI Structured Outputs · structlog · trafilatura.

---

## Configuration

All settings via env vars or a `.env` file. Key vars:

| Var | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | Required (or pass via `openai_api_key=` kwarg) |
| `OPENAI_MODEL_INTENT` | `gpt-4o-mini` | Intent parser model |
| `OPENAI_MODEL_PLAN` | `gpt-4.1` | Planner + repair + semantic model |
| `OPENAI_MODEL_REPAIR` | `gpt-4.1` | Repair model |
| `DB_URL` | `sqlite+aiosqlite:///./spectus.db` | Swap to `postgresql+asyncpg://...` for Postgres |
| `ARTIFACTS_DIR` | `./artifacts` | Per-job debug bundles |
| `BROWSER_POOL_SIZE` | `3` | Playwright contexts |
| `BROWSER_HEADLESS` | `true` | Headless mode |
| `RATE_LIMIT_RPS` | `1.0` | Per-domain token-bucket refill |
| `ALLOW_PRIVATE_TARGETS` | `false` | Set `true` only for local fixture testing |
| `JOB_DEADLINE_SEC` | `180` | Hard wall-time per request |
| `LLM_INTENT_TIMEOUT_SEC` | `45` | Per-call timeout for intent parser |
| `LLM_PLANNER_TIMEOUT_SEC` | `60` | Per-call timeout for planner |
| `LLM_REPAIR_TIMEOUT_SEC` | `60` | Per-call timeout for repair |

GPT-5 / o-series support: pass `OPENAI_MODEL_*=gpt-5-nano` and bump `LLM_*_TIMEOUT_SEC` (reasoning tokens take longer). Client auto-uses `max_completion_tokens` + `reasoning_effort=low` for those models.

Pass overrides programmatically:

```python
from spectus import Client

client = await Client.create(
    openai_api_key="sk-...",
    settings={
        "openai_model_intent": "gpt-4o-mini",
        "openai_model_plan":   "gpt-5-nano",
        "browser_pool_size":   1,
        "allow_private_targets": False,
    },
)
```

---

## Compliance + safety (built-in)

- SSRF: blocks private / loopback / link-local / reserved IPs before any fetch.
- Robots.txt: 1h-TTL cache, fail-open on 5xx.
- Per-domain rate-limit token bucket.
- Allowed selector attributes: `text`, `href`, `src`, `alt`, `title`, `class`, `id`, `value`, `data-*`, `aria-*`. Anything else rejected at Pydantic boundary.
- jQuery extensions (`:has()`, `:is()`, `:visible`, etc.) rejected before reaching the parser. `:contains('text')` is translated server-side (lexbor CSS + text filter).
- No CAPTCHA solve, no auth bypass, no anti-bot evasion. Out of scope by design.

---

## Develop from source

```bash
git clone https://github.com/Mrrobi/spectus
cd spectus
uv sync --extra dev --extra notebook
uv run playwright install chromium
uv run alembic upgrade head
cp .env.example .env                  # add your OPENAI_API_KEY
make dev                              # uvicorn --reload on :8000
```

```bash
make test         # pytest -n auto with coverage
make test-fast    # skip @browser-marked tests
make lint         # ruff
make format       # ruff fix + format
make typecheck    # mypy strict
make clean        # drop DB + artifacts + cache
```

Suite: 52 unit tests, runs <1s offline. Plus `@pytest.mark.browser` for real Chromium.

CI runs on every push to `main` and every PR (Linux + Windows + macOS). See `.github/workflows/`.

---

## License

MIT.
