# spectus — recipes

Copy-paste examples for common targets. All assume:

```bash
pip install spectus
spectus install-browsers
export OPENAI_API_KEY=sk-...          # Windows PowerShell:  $env:OPENAI_API_KEY="sk-..."
```

---

## Table of contents

1. [Hacker News front page (list)](#1-hacker-news-front-page-list-extraction)
2. [Real-estate listing — Norwegian finn.no (single, semantic fallback)](#2-real-estate-listing--norwegian-finnno-single-entity-semantic-fallback)
3. [E-commerce product listing (template cache)](#3-e-commerce-product-listing-template-cached-path)
4. [JavaScript-rendered SPA (browser path)](#4-javascript-rendered-spa-browser-path)
5. [Article extraction (clean body + metadata)](#5-article-extraction-clean-body--metadata)
6. [HTML table](#6-html-table)
7. [Multi-stage: follow an extracted link](#7-multi-stage-follow-a-link-extracted-in-step-1)
8. [Save to CSV / JSON / pandas](#8-save-to-csv--json--pandas)
9. [CLI one-liners](#9-cli-one-liners)
10. [Tuning behaviour](#10-tuning-behaviour)
11. [Async usage (FastAPI / aiohttp / asyncio)](#11-async-usage-fastapi--aiohttp--asyncio)
12. [Error handling](#12-error-handling)
13. [Read diagnostics](#13-diagnostics--what-just-happened)
14. [Debug artifacts on disk](#14-debug-artifacts-on-disk)
15. [Common gotchas](#15-common-gotchas)

---

## 1. Hacker News front page (list extraction)

```python
from spectus import extract

result = extract(
    url="https://news.ycombinator.com/",
    instruction=(
        "Extract the top stories. For each story: title, points, author, "
        "comments_count, story_url."
    ),
    max_records=30,
)

for row in result["records"]:
    title = row.get("title") or "(no title)"
    points = row.get("points")
    url = row.get("story_url") or ""
    print(f"[{str(points):>4}] {title}  ({url})")
```

---

## 2. Real-estate listing — Norwegian finn.no (single-entity, semantic fallback)

```python
from spectus import extract

result = extract(
    url="https://www.finn.no/realestate/homes/ad.html?finnkode=463730293",
    instruction=(
        "Return one record: viewing_time, asking_price (NOK integer), "
        "sales_doc_url."
    ),
    max_records=1,
)
print(result["records"][0])
# {'viewing_time':   '2026-05-26T14:00:00Z',
#  'asking_price':   2090000,
#  'sales_doc_url':  'https://dnbeiendom.no/702260220?...salgsoppgave'}
```

spectus automatically falls back to **semantic LLM extraction** when CSS selectors fail — works on sites with no semantic class names (finn.no is a known hard target).

---

## 3. E-commerce product listing (template-cached path)

```python
from spectus import SyncClient

with SyncClient.open() as client:
    # First call: cold path, builds and saves a template (~10s).
    r1 = client.extract(
        "https://books.toscrape.com/",
        "Extract every book: title, price, availability, rating, link.",
        max_records=40,
    )

    # Same domain + same field-set: template hit (~3s, planner LLM skipped).
    r2 = client.extract(
        "https://books.toscrape.com/catalogue/page-2.html",
        "Extract every book: title, price, availability, rating, link.",
        max_records=40,
    )
```

Templates promote `candidate → active` after 3 consecutive successful runs and survive across process restarts (stored in the SQLite DB).

---

## 4. JavaScript-rendered SPA (browser path)

```python
from spectus import extract

result = extract(
    url="http://quotes.toscrape.com/js/",
    instruction="Extract each quote: text, author, tags (list).",
    use_browser="force",                  # SPA — must render with Chromium
    max_records=20,
)
```

Tip: pass `use_browser="auto"` (default) and spectus decides. Pass `"force"` only when you already know the page is JS-only. Pass `"never"` to skip Chromium entirely (faster, cheaper, but fails on SPAs).

---

## 5. Article extraction (clean body + metadata)

```python
from spectus import extract

result = extract(
    url="https://en.wikipedia.org/wiki/Python_(programming_language)",
    instruction=(
        "One record with: title, summary (first paragraph), and the full body text."
    ),
    max_records=1,
)
record = result["records"][0]
print(record["title"])
print(record["body"][:500])
```

Behind the scenes this uses `article_extraction` (trafilatura) which strips nav / footer / sidebars and returns just the article content.

---

## 6. HTML table

```python
from spectus import extract

result = extract(
    url="https://en.wikipedia.org/wiki/List_of_countries_and_dependencies_by_population",
    instruction=(
        "Extract the main country population table. Each row: rank, "
        "country, population (integer), percent (number)."
    ),
    max_records=20,
)
```

**Note:** complex tables with merged cells, flag-image columns, or footnotes can produce partial results. Check `result["diagnostics"]["quality_score"]` and fall back to a single-cell extraction if needed.

---

## 7. Multi-stage: follow a link extracted in step 1

```python
from spectus import SyncClient

with SyncClient.open() as client:
    # Step 1: get the external sales-doc link from the finn listing
    r1 = client.extract(
        "https://www.finn.no/realestate/homes/ad.html?finnkode=463730293",
        "Return sales_doc_url for this property.",
        max_records=1,
    )
    sales_url = r1["records"][0]["sales_doc_url"]

    # Step 2: visit that page, extract the actual PDF link
    r2 = client.extract(
        sales_url,
        "Find the PDF link to the complete salgsoppgave. Return pdf_url.",
        use_browser="force",
        max_records=1,
    )
    pdf_url = r2["records"][0]["pdf_url"]
    print(pdf_url)
```

The SyncClient reuses the browser pool across both calls, so the second extraction doesn't pay browser-startup cost.

---

## 8. Save to CSV / JSON / pandas

```python
import csv, json
from pathlib import Path
from spectus import extract

result = extract(url=..., instruction=...)
records = result["records"]

# JSON
Path("out.json").write_text(
    json.dumps(records, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

# CSV
fieldnames = list(records[0].keys()) if records else []
with open("out.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(records)

# Pandas
import pandas as pd
df = pd.DataFrame(records)
df.to_parquet("out.parquet")
df.to_excel("out.xlsx", index=False)
```

---

## 9. CLI one-liners

```bash
# Pipe CSV out for shell tooling
spectus extract https://news.ycombinator.com/ \
    "Top stories: title, points, author, story_url" --output csv > hn.csv

# Pipe JSON into jq for inspection
spectus extract https://example.com/products \
    "Each product: name, price, link" --output json | jq '.[0:5]'

# List saved templates
spectus templates --output json | jq

# Run as a quick smoke test
spectus extract https://example.com "page title and first heading" --output table

# Force static-only (fastest, cheapest)
spectus extract https://news.ycombinator.com/ "title, points, story_url" \
    --browser never --max-records 20 --output json
```

---

## 10. Tuning behaviour

```python
from spectus import Client

client = await Client.create(
    openai_api_key="sk-...",
    settings={
        # Cheaper / faster models:
        "openai_model_intent":   "gpt-4o-mini",
        "openai_model_plan":     "gpt-5-nano",
        "openai_model_repair":   "gpt-5-nano",

        # Reasoning models need more time:
        "llm_intent_timeout_sec":   45.0,
        "llm_planner_timeout_sec":  60.0,
        "llm_repair_timeout_sec":   60.0,
        "job_deadline_sec":         180.0,

        # Lean: only one browser context (less memory):
        "browser_pool_size": 1,

        # Nice-scraping: slow per-domain:
        "rate_limit_rps": 0.5,
    },
)
```

For one-shot `extract()`, the same options go through the `settings={}` kwarg:

```python
from spectus import extract
extract(url, instruction, settings={"openai_model_plan": "gpt-4o-mini"})
```

---

## 11. Async usage (FastAPI / aiohttp / asyncio)

If your code already runs an event loop, use the async `Client`:

```python
import asyncio
from spectus import Client


async def main():
    client = await Client.create(openai_api_key="sk-...")
    try:
        result = await client.extract(
            "https://news.ycombinator.com/",
            "Top stories: title, story_url",
            max_records=10,
        )
        return result
    finally:
        await client.close()


asyncio.run(main())
```

Sync `extract()` and `SyncClient` also work from inside a running loop (e.g. Jupyter) — they transparently dispatch to a background thread. No `nest_asyncio` needed.

### Async batched

```python
import asyncio
from spectus import Client


async def main(urls):
    client = await Client.create()
    try:
        tasks = [
            client.extract(u, "extract title and main link", max_records=5)
            for u in urls
        ]
        # Sequential is usually right — extraction itself runs in parallel
        # against the LLM, but multiple browser contexts compete for the pool.
        results = []
        for t in tasks:
            results.append(await t)
        return results
    finally:
        await client.close()


asyncio.run(main([
    "https://example.com",
    "https://news.ycombinator.com",
]))
```

---

## 12. Error handling

Hard failures raise typed exceptions (subclasses of `spectus.errors.ExtractionError`):

```python
from spectus import extract
from spectus.errors import (
    InvalidUrlError,
    BlockedUrlError,
    BlockedByRobotsError,
    FetchError,
    LlmTransientError,
    JobTimeoutError,
    ExtractionError,
)

try:
    result = extract(url, instruction)
except InvalidUrlError as e:
    print(f"bad url: {e.detail}")
except BlockedUrlError as e:
    print(f"SSRF blocked: {e.detail}")            # private IP, internal target
except BlockedByRobotsError as e:
    print(f"robots.txt forbids: {e.detail}")
except FetchError as e:
    print(f"network: {e.detail}")
except LlmTransientError as e:
    print(f"OpenAI unavailable: {e.detail}")      # retryable
except JobTimeoutError as e:
    print(f"exceeded budget: {e.detail}")
except ExtractionError as e:
    print(f"other extraction error: {e.code} / {e.detail}")
```

**Soft failures** don't raise — they return a result with `status="partial_success"` or `"failed"`, populated `message`, and whatever records could be salvaged. Check `result["status"]`:

```python
result = extract(url, instruction)
if result["status"] == "success":
    use(result["records"])
elif result["status"] == "partial_success":
    log.warn("partial: %s", result["message"])
    use(result["records"])                         # may be incomplete
else:
    log.error("extraction failed: %s", result["message"])
```

---

## 13. Diagnostics — what just happened?

Every result includes a `diagnostics` block:

```python
result = extract(url, instruction)
d = result["diagnostics"]

print(f"strategy:         {d['strategy_used']}")          # how it found the data
print(f"mode:             {d['static_or_browser']}")      # static fetch or Chromium
print(f"quality_score:    {d['quality_score']}")          # 0..1
print(f"repair_attempts:  {d['repair_attempts']}")        # 0..2
print(f"template_used:    {d['template_used']}")          # warm path?
print(f"llm_calls:        {d['llm_calls']}")
print(f"llm_tokens_in:    {d['llm_tokens_in']}")
print(f"llm_tokens_out:   {d['llm_tokens_out']}")
print(f"runtime_ms:       {d['runtime_ms']}")
print(f"warnings:         {d['warnings']}")
```

Use `quality_score < 0.8` as a signal to manually verify the output.

---

## 14. Debug artifacts on disk

Every job writes a debug bundle to `./artifacts/{job_id}/`:

```
raw.html                 - what httpx fetched
rendered.html            - what Chromium rendered (if browser path)
screenshot.png           - viewport screenshot
compact.json             - the page representation sent to the planner
intent.json              - field schema inferred from your instruction
plan.json                - selectors / strategy chosen by the planner
validation.json          - quality scoring breakdown
semantic_result.json     - LLM-from-text-bundle output (if used)
merged_validation.json   - score after merging standard + semantic
llm/intent.1.json        - full LLM I/O for intent call
llm/planner.1.json       - full LLM I/O for planner call
llm/repair_1.1.json      - full LLM I/O for repair (if any)
llm/semantic.1.json      - full LLM I/O for semantic pass (if any)
error.json               - on failure
```

Inspect these when a low-quality extraction or selector mismatch is hard to explain. They're the same things attached to a good bug report.

---

## 15. Common gotchas

- **Prices as integers vs floats.** `asking_price: 5490000` is correct for NOK; for USD `"$89.99"` you'd want `"number"` or `"currency"` field type. Asking for `integer` on "$89.99" gives `89`.
- **Norwegian / non-ASCII characters.** Always pass `ensure_ascii=False` to `json.dumps()`, and write files with `encoding="utf-8"`. spectus stores everything as UTF-8 internally.
- **Templates can lock in a bad plan.** If a saved template starts producing junk after a site redesign, drop it: `sqlite3 spectus.db "DELETE FROM extraction_templates WHERE domain='example.com'"` (or call the API). spectus auto-deprecates templates after 5 consecutive failures, but you can speed that up.
- **`max_records` is a cap, not a quota.** If the page has 3 products and you ask for 50, you get 3. If it has 200 and you ask for 50, you get the first 50.
- **Hacker News points / comments are noisy on cold start.** Once the template hits `active`, accuracy is consistent.
- **`use_browser="auto"` sometimes picks `static` for an SPA.** The heuristic looks at text length and structured-data presence; if it misjudges, force with `use_browser="force"`.
- **Chromium memory.** Each `BROWSER_POOL_SIZE` adds ~200 MB resident. Default is 3. Set to 1 on small VMs.
- **OPENAI_API_KEY in a child process.** `subprocess.run()` doesn't inherit env vars unless you `env=os.environ.copy()`. If `spectus.errors.LlmTransientError: openai_not_configured` fires, this is usually why.
