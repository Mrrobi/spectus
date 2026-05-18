# spectus — recipes

Copy-paste examples for common targets. All assume:

```bash
pip install spectus
spectus install-browsers
export OPENAI_API_KEY=sk-...
```

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
    print(f"[{row.get('points', '?'):>3}] {row['title']}  ({row.get('story_url')})")
```

---

## 2. Real estate listing — Norwegian finn.no (single-entity, semantic fallback)

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
# {'viewing_time': '2026-05-26T14:00:00Z',
#  'asking_price': 2090000,
#  'sales_doc_url': 'https://dnbeiendom.no/702260220?...salgsoppgave'}
```

`spectus` automatically falls back to semantic LLM extraction when CSS selectors fail — works on sites with no semantic class names.

---

## 3. E-commerce product listing (template-cached path)

```python
from spectus import SyncClient

with SyncClient.open() as client:
    # First call: cold, builds template (~10s)
    r1 = client.extract(
        "https://books.toscrape.com/",
        "Extract every book: title, price, availability, rating, link.",
        max_records=40,
    )

    # Same domain + same fields: template hit (~3s, planner LLM skipped)
    r2 = client.extract(
        "https://books.toscrape.com/catalogue/page-2.html",
        "Extract every book: title, price, availability, rating, link.",
        max_records=40,
    )
```

---

## 4. JavaScript-rendered SPA (browser path)

```python
from spectus import extract

result = extract(
    url="http://quotes.toscrape.com/js/",
    instruction="Extract each quote: text, author, tags (list).",
    use_browser="force",      # SPA — must render with Chromium
)
```

---

## 5. Article extraction (clean body + metadata)

```python
from spectus import extract

result = extract(
    url="https://en.wikipedia.org/wiki/Python_(programming_language)",
    instruction=(
        "One record: title, summary (first paragraph), and the full body text."
    ),
    max_records=1,
)
record = result["records"][0]
print(record["title"])
print(record["body"][:500])
```

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

---

## 7. Multi-stage: follow a link extracted in step 1

```python
from spectus import SyncClient

with SyncClient.open() as client:
    # Step 1: get listing's external link
    r1 = client.extract(
        "https://www.finn.no/realestate/homes/ad.html?finnkode=463730293",
        "Return sales_doc_url for this property.",
        max_records=1,
    )
    sales_url = r1["records"][0]["sales_doc_url"]

    # Step 2: visit it, extract PDF link
    r2 = client.extract(
        sales_url,
        "Find the PDF link to the complete salgsoppgave. Return pdf_url.",
        use_browser="force",
        max_records=1,
    )
    print(r2["records"][0]["pdf_url"])
```

---

## 8. Save to CSV / JSON / pandas

```python
import csv, json
from spectus import extract

result = extract(url=..., instruction=...)

# JSON
with open("out.json", "w", encoding="utf-8") as f:
    json.dump(result["records"], f, ensure_ascii=False, indent=2)

# CSV
fieldnames = list(result["records"][0].keys()) if result["records"] else []
with open("out.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(result["records"])

# Pandas
import pandas as pd
df = pd.DataFrame(result["records"])
df.to_parquet("out.parquet")
```

---

## 9. CLI one-liners

```bash
spectus extract https://news.ycombinator.com/ \
    "Top stories: title, points, author, story_url" --output csv > hn.csv

spectus extract https://example.com/products \
    "Each product: name, price, link" --output json | jq '.[0:5]'

spectus templates --output json | jq
```

---

## 10. Tuning behaviour

```python
from spectus import Client

client = await Client.create(
    openai_api_key="sk-...",
    settings={
        # Pick cheaper / faster model:
        "openai_model_intent":   "gpt-4o-mini",
        "openai_model_plan":     "gpt-5-nano",
        "openai_model_repair":   "gpt-5-nano",

        # Generous timeouts for reasoning models:
        "llm_intent_timeout_sec":   45.0,
        "llm_planner_timeout_sec":  60.0,
        "llm_repair_timeout_sec":   60.0,
        "job_deadline_sec":         180.0,

        # Fewer browser contexts on small machines:
        "browser_pool_size": 1,

        # Strict rate-limit for nice scraping:
        "rate_limit_rps": 0.5,
    },
)
```

---

## 11. Diagnostics — what just happened?

Every result includes a `diagnostics` block:

```python
result = extract(url, instruction)

d = result["diagnostics"]
print(f"strategy:        {d['strategy_used']}")       # how it found the data
print(f"mode:            {d['static_or_browser']}")   # static fetch or Chromium
print(f"quality_score:   {d['quality_score']}")       # 0..1
print(f"repair_attempts: {d['repair_attempts']}")     # 0..2
print(f"template_used:   {d['template_used']}")       # warm path?
print(f"llm_calls:       {d['llm_calls']}")
print(f"runtime_ms:      {d['runtime_ms']}")
print(f"warnings:        {d['warnings']}")
```

Use `quality_score < 0.8` as a signal to manually verify the output.

---

## 12. Debug artifacts on disk

Every job writes to `./artifacts/{job_id}/`:

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

Inspect these to understand why a low-quality extraction happened or to debug selector mismatches.
