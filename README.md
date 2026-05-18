<!-- ASCII banner -->
<pre align="center">
                          _
   ___ _ __   ___  ___ | |_ _   _ ___
  / __| '_ \ / _ \/ __|| __| | | / __|
  \__ \ |_) |  __/ (__ | |_| |_| \__ \
  |___/ .__/ \___|\___| \__|\__,_|___/
      |_|     AI-driven web extractor
</pre>

<p align="center">
  <a href="https://pypi.org/project/spectus/"><img src="https://img.shields.io/pypi/v/spectus.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/spectus/"><img src="https://img.shields.io/pypi/pyversions/spectus.svg" alt="Python"></a>
  <a href="https://github.com/Mrrobi/spectus/actions/workflows/test.yml"><img src="https://img.shields.io/github/actions/workflow/status/Mrrobi/spectus/test.yml?branch=main&label=tests" alt="tests"></a>
  <a href="https://github.com/Mrrobi/spectus/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
</p>

**spectus** — paste a URL, describe what you want in plain English, get structured JSON or CSV. Resilient to DOM changes: when CSS selectors fail, falls back automatically to **semantic LLM extraction** over a facts bundle (structured data + visible text + anchors + label-value pairs). Same loop on any site; no per-site rules.

```
$ spectus extract https://news.ycombinator.com/ "Top stories: title, points, author, story_url" --output csv
title,points,author,story_url
Mercurial, 20 years and counting,70,ibobev,https://fosdem.org/...
...
```

---

## Install

```bash
pip install spectus
spectus install-browsers              # one-time Playwright Chromium download (~110 MB)
export OPENAI_API_KEY=sk-...          # Windows PowerShell:  $env:OPENAI_API_KEY="sk-..."
```

Requires Python 3.10+ (tested on 3.10 / 3.11 / 3.12 / 3.13). Linux / macOS / Windows.

---

## 30-second tour

### CLI

```bash
spectus extract https://example.com/products \
    "Each product: title, price, rating, link" --output json
```

### Python (sync — works in Jupyter too)

```python
from spectus import extract

result = extract(
    url="https://example.com/products",
    instruction="Each product: title, price, rating, link",
    openai_api_key="sk-...",          # optional; falls back to OPENAI_API_KEY env
)
print(result["records"])              # list[dict]
print(result["diagnostics"])          # strategy, quality_score, tokens, ...
```

### Python (batched — reuses browser pool)

```python
from spectus import SyncClient

with SyncClient.open(openai_api_key="sk-...") as client:
    r1 = client.extract(url1, "extract X, Y, Z")
    r2 = client.extract(url2, "another instruction")
```

### Python (async — for FastAPI / aiohttp / asyncio code)

```python
from spectus import Client

client = await Client.create(openai_api_key="sk-...")
result = await client.extract(url, instruction)
await client.close()
```

More patterns in [EXAMPLES.md](https://github.com/Mrrobi/spectus/blob/main/EXAMPLES.md).

---

## Why spectus

- **No selectors to maintain.** You describe the data; the system finds it.
- **Survives DOM changes.** Semantic fallback reads page meaning, not CSS class names.
- **Learns per domain.** Successful extractions become templates → 3–5× faster on subsequent calls, planner LLM skipped.
- **Built-in safety.** SSRF gate, robots.txt cache, per-domain rate limit. No CAPTCHA solving, no auth bypass.
- **Debug-friendly.** Every job writes a full artifact bundle to disk: raw HTML, rendered HTML, screenshots, compact page representation, every LLM I/O, validation report.

---

## What you get back

`extract()` always returns a plain `dict`:

```python
{
  "status": "success" | "partial_success" | "failed",
  "url": "...",
  "instruction": "...",
  "records": [ {...}, {...}, ... ],          # list of dicts; single dict for single-entity
  "diagnostics": {
    "strategy_used":    "semantic_extraction" | "repeated_dom_selector" | ...,
    "page_type":        "article" | "product_listing" | ...,
    "static_or_browser": "static" | "browser",
    "records_found":    int,
    "quality_score":    0.0 - 1.0,
    "field_coverage":   {field_name: 0.0-1.0},
    "missing_required": {field_name: count},
    "repair_attempts":  int,
    "template_used":    bool,
    "template_id":      uuid | null,
    "runtime_ms":       int,
    "llm_calls":        int,
    "llm_tokens_in":    int,
    "llm_tokens_out":   int,
    "warnings":         [str, ...]
  },
  "message": null | "repair hint when partial"
}
```

---

## How it works (one paragraph)

Every request runs: URL normalize → SSRF + robots + rate-limit → parallel(intent-LLM, static-fetch + analyze) → template lookup → planner-LLM → executor → validator → repair loop (≤ 2 attempts) → **resilience pass: semantic LLM extraction over a facts bundle, per-field merge with type-aware tie-breakers** → save winning strategy as template → return JSON or CSV with diagnostics.

Seven extraction strategies, chosen automatically:

| Strategy | When |
|---|---|
| `structured_data` | JSON-LD / OpenGraph / `__NEXT_DATA__` / `__NUXT__` present |
| `repeated_dom_selector` | Repeating containers (cards / rows / tiles) detected |
| `single_dom_selector` | Page-level data with clear DOM hooks |
| `table_extraction` | HTML tables with sensible headers |
| `article_extraction` | Long-form content (article, blog, encyclopedia) |
| `visible_text_regex` | Fallback regex over visible text |
| `semantic_extraction` | LLM reads facts bundle — no DOM dependency, **survives DOM redesigns** |

---

## CLI reference

```
spectus extract URL "instruction"  [--browser auto|force|never] [--max-records N] [--output table|json|csv]
spectus templates                  [--status candidate|active|needs_review|deprecated] [--output table|json]
spectus migrate
spectus install-browsers
spectus version
```

---

## Configuration

Set via env var (or pass to `Client.create(settings={...})`).

| Var | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | Required (or pass as `openai_api_key=` kwarg) |
| `OPENAI_MODEL_INTENT` | `gpt-4o-mini` | Intent parser model |
| `OPENAI_MODEL_PLAN` | `gpt-4.1` | Planner + semantic model |
| `OPENAI_MODEL_REPAIR` | `gpt-4.1` | Repair model |
| `DB_URL` | `sqlite+aiosqlite:///./spectus.db` | Swap to `postgresql+asyncpg://...` for Postgres |
| `ARTIFACTS_DIR` | `./artifacts` | Per-job debug bundles |
| `BROWSER_POOL_SIZE` | `3` | Playwright contexts |
| `RATE_LIMIT_RPS` | `1.0` | Per-domain token-bucket refill |
| `ALLOW_PRIVATE_TARGETS` | `false` | Set `true` only for local fixture testing |
| `JOB_DEADLINE_SEC` | `180` | Hard wall-time per request |
| `LLM_INTENT_TIMEOUT_SEC` | `45` | Intent parser timeout |
| `LLM_PLANNER_TIMEOUT_SEC` | `60` | Planner timeout |
| `LLM_REPAIR_TIMEOUT_SEC` | `60` | Repair timeout |

**GPT-5 / o-series support**: pass `OPENAI_MODEL_*=gpt-5-nano` and bump timeouts. Client auto-uses `max_completion_tokens` + `reasoning_effort=low` for those models.

---

## Compliance + safety (built-in)

- SSRF: blocks private / loopback / link-local / reserved IPs before any fetch.
- Robots.txt: 1h-TTL cache, fail-open on 5xx.
- Per-domain rate-limit token bucket.
- Allowed selector attributes: `text`, `href`, `src`, `srcset`, `alt`, `title`, `class`, `id`, `value`, `content`, `datetime`, `name`, `type`, `role`, `placeholder`, `download`, `rel`, `property`, `lang`, `data-*`, `aria-*`. Anything else rejected at the Pydantic boundary.
- jQuery extensions (`:has()`, `:is()`, `:visible`, etc.) rejected. `:contains('text')` translated server-side.
- No CAPTCHA solve, no auth bypass, no anti-bot evasion. Out of scope by design.

---

## Links

- **Examples**: [EXAMPLES.md](https://github.com/Mrrobi/spectus/blob/main/EXAMPLES.md) — 12 recipes
- **Source / issues**: [github.com/Mrrobi/spectus](https://github.com/Mrrobi/spectus)
- **Contributing / dev loop**: [CONTRIBUTING.md](https://github.com/Mrrobi/spectus/blob/main/CONTRIBUTING.md)

---

## License

[MIT](https://github.com/Mrrobi/spectus/blob/main/LICENSE) © 2026 Mrrobi
