# AI-Assisted Web Data Extractor - Version 1 Plan

## 1. Product Summary

The goal of Version 1 is to build a system where a user can paste a URL, describe in natural language what data they want, and receive structured output such as JSON, CSV, or a table preview.

The system should not try to invent a new scraping engine. Instead, it should use proven scraping and browser automation tools as the execution layer, while adding a small intelligent AI layer that understands the user's intent, chooses an extraction strategy, generates extraction rules, validates results, and repairs failures.

### One-line product idea

> Paste a URL, say what data you need, and get clean structured data without writing scraping code.

### Example user flow

```text
User input:
URL: https://example.com/products
Instruction: Extract all product names, prices, ratings, and availability.

System output:
[
  {
    "name": "Nike Running Shoe",
    "price": "$89.99",
    "rating": "4.7",
    "availability": "In stock"
  }
]
```

---

## 2. V1 Objective

Version 1 should prove that the system can reliably perform prompt-based extraction from common web pages.

### Main V1 objective

Build a working single-URL intelligent extractor that can:

1. Accept a URL and natural language instruction.
2. Load the web page using static or dynamic rendering.
3. Understand what fields the user wants.
4. Identify where the relevant data exists on the page.
5. Extract the data into a structured schema.
6. Validate the output.
7. Return JSON and optionally CSV.
8. Save successful extraction patterns for reuse.

### What V1 should feel like to the user

The user should not need to know:

- CSS selectors
- XPath
- HTML structure
- Whether the page is static or dynamic
- Whether the data is inside JSON-LD, script tags, tables, cards, or rendered JavaScript
- How pagination works
- How to clean and normalize text

The user should only provide:

```text
1. A URL
2. A plain-English instruction
```

---

## 3. V1 Scope

### In scope

V1 should support:

1. Single URL extraction
2. Static HTML pages
3. JavaScript-rendered pages
4. Product/listing/card pages
5. Article/content pages
6. HTML table extraction
7. Repeated item extraction from a page
8. Single entity extraction from a page
9. JSON output
10. CSV export
11. Screenshot and HTML snapshot storage for debugging
12. Basic extraction retry/repair loop
13. Domain-level template saving
14. Basic rate limiting
15. Basic robots.txt/compliance check

### Out of scope for V1

Avoid these in V1 unless absolutely necessary:

1. Login-gated scraping
2. Paywall bypassing
3. CAPTCHA solving
4. Heavy anti-bot evasion
5. Massive multi-site crawling
6. Long-running scheduled scraping
7. Deep recursive crawling
8. Browser fingerprint spoofing
9. Complex user accounts and teams
10. Marketplace of extraction templates
11. Real-time monitoring and alerts
12. Full enterprise permission management

### Reason for this scope

The V1 product should prove the core intelligence layer, not become an infrastructure-heavy crawler too early.

The risky/valuable part is:

> Can the system translate a human instruction into a reliable extraction plan and produce useful structured data?

---

## 4. Recommended V1 Tech Stack

### Backend

Use Python FastAPI.

Reason:

- Fast to build
- Good ecosystem for scraping and AI orchestration
- Easy API creation
- Works well with Pydantic validation
- Easy to run background jobs later

### Static fetching

Use:

- `httpx`
- `BeautifulSoup`
- `lxml`
- `selectolax` optional

Purpose:

- Fast static HTML fetch
- Low cost
- Useful for simple pages
- Avoid browser overhead when not needed

### Dynamic rendering

Use Playwright.

Purpose:

- Render JavaScript-heavy pages
- Wait for network idle or target selectors
- Capture screenshots
- Inspect visible DOM
- Evaluate scripts when needed

### Crawling and queue layer

For V1, you can start without a full crawling framework. But if you want a stronger base from day one, use Crawlee with Playwright.

Recommended choice:

- If building mostly in Python: start with custom Playwright workers.
- If comfortable with TypeScript/Node: use Crawlee + Playwright.

### Article/text extraction

Use Trafilatura.

Purpose:

- Extract clean article text
- Extract metadata
- Reduce boilerplate
- Useful for blogs, news pages, documentation pages, and content-heavy pages

### Optional fallback providers

Do not depend on these for the core V1, but design the system so they can be plugged in later:

- Firecrawl
- Zyte API
- Browserless

Use these only when:

- Your internal static parser fails
- Playwright fails
- Infrastructure becomes expensive to maintain
- A page requires managed browser infrastructure

### AI layer

Start with a hosted LLM for speed. Later, experiment with a local model for cost and privacy.

Recommended V1 approach:

- Use a strong hosted model for planning and schema generation during prototype.
- Keep prompts and outputs structured so the model can later be swapped.
- Store model input/output traces for debugging.
- Do not make the whole product depend on model free-form text.

### Data validation

Use Pydantic.

Purpose:

- Validate extracted records
- Normalize field types
- Detect missing required values
- Return consistent errors to the repair loop

### Storage

Use Postgres for metadata and S3-compatible object storage for artifacts.

For a local MVP:

- SQLite or Postgres
- Local filesystem for HTML and screenshots

For production V1:

- Postgres
- S3/R2/MinIO for artifacts

### Queue

Start simple:

- Synchronous API for small jobs
- Background task for browser jobs

Then add:

- Redis + RQ
- or Redis + Celery
- or Dramatiq

---

## 5. High-Level Architecture

```text
+-------------------+
| User Interface    |
| URL + Instruction |
+---------+---------+
          |
          v
+-------------------+
| API Backend       |
| FastAPI           |
+---------+---------+
          |
          v
+-------------------+
| Intent Parser     |
| AI schema builder |
+---------+---------+
          |
          v
+-------------------+
| Page Fetcher      |
| Static first      |
+---------+---------+
          |
          v
+-------------------+
| Page Classifier   |
| static/dynamic    |
| article/list/table|
+---------+---------+
          |
          v
+-------------------+
| Extraction Planner|
| AI + heuristics   |
+---------+---------+
          |
          v
+-------------------+
| Extraction Engine |
| selectors/rules   |
+---------+---------+
          |
          v
+-------------------+
| Validator         |
| Pydantic/schema   |
+---------+---------+
          |
          v
+-------------------+
| Repair Loop       |
| retry if needed   |
+---------+---------+
          |
          v
+-------------------+
| Output Formatter  |
| JSON/CSV/table    |
+-------------------+
```

---

## 6. Core Design Principle

The AI should not directly scrape websites.

Instead:

```text
AI plans. Deterministic tools execute. Validator checks. AI repairs only when needed.
```

This is important because direct AI extraction from raw HTML is expensive, inconsistent, and hard to debug.

Better approach:

1. Use deterministic tools to fetch and parse.
2. Convert the page into a compact representation.
3. Ask AI to create a structured extraction plan.
4. Execute that plan with code.
5. Validate output.
6. Retry with more context only if needed.

---

## 7. V1 User Stories

### User story 1: Extract product listings

As a user, I want to paste a product category URL and ask for product names, prices, ratings, and links, so that I can export product data without writing code.

Acceptance criteria:

- User enters URL and instruction.
- System returns a list of product records.
- Each record has requested fields where available.
- Output can be downloaded as CSV.

### User story 2: Extract a table

As a user, I want to paste a page containing a table and ask the system to extract it, so I can get clean CSV or JSON.

Acceptance criteria:

- System detects HTML tables.
- System maps table headers to fields.
- System returns rows in JSON and CSV.

### User story 3: Extract article information

As a user, I want to extract article title, author, date, summary, and main content from an article URL.

Acceptance criteria:

- System detects article-like page.
- System uses text extraction mode.
- Output contains title, author/date when available, and main body text.

### User story 4: Extract company/contact info

As a user, I want to extract company name, phone number, email, address, and social links from a webpage.

Acceptance criteria:

- System extracts page-level information.
- System recognizes this as single-entity extraction, not a repeated list.
- Output is one JSON object, not an array.

### User story 5: Save reusable extractor

As a user, I want the system to remember how it extracted data from a domain so future runs are faster and more reliable.

Acceptance criteria:

- System stores domain, page type, selectors, and field mapping.
- On future URL from same domain/page type, system attempts stored template first.
- If template fails, system re-plans.

---

## 8. V1 Extraction Modes

The system should support multiple extraction strategies and choose the cheapest reliable option first.

### Mode 1: Structured data extraction

Look for:

- JSON-LD
- schema.org markup
- OpenGraph tags
- Twitter card tags
- embedded product/article metadata
- Next.js data blocks such as `__NEXT_DATA__`
- Nuxt or other framework hydration data

Use this mode first because it is often clean and cheap.

### Mode 2: Static DOM selector extraction

Use this when data is present in HTML.

Steps:

1. Fetch HTML.
2. Parse DOM.
3. Find repeated blocks.
4. Generate candidate selectors.
5. Extract fields.
6. Validate.

### Mode 3: Table extraction

Use this when page contains HTML tables.

Steps:

1. Detect tables.
2. Extract headers.
3. Extract rows.
4. Ask AI to map fields if user instruction asks for a subset.
5. Return structured table data.

### Mode 4: Article/text extraction

Use this for pages that are mostly text.

Steps:

1. Use Trafilatura/readability-style extraction.
2. Extract title, text, author/date if available.
3. Use AI only to shape output into requested schema.

### Mode 5: Dynamic browser extraction

Use this when static HTML does not contain enough content.

Triggers:

- Static HTML is too small.
- Page contains app shell only.
- Many script tags but little visible text.
- User asks for content that appears after interaction.
- Product/listing data is not in fetched HTML.

Steps:

1. Launch Playwright.
2. Navigate to URL.
3. Wait for page load.
4. Capture visible text and DOM snapshot.
5. Detect repeated sections.
6. Generate selectors.
7. Extract fields from rendered DOM.

### Mode 6: AI-assisted fallback extraction

Use this only when selector-based extraction fails.

Inputs to AI:

- User instruction
- Compact visible text blocks
- Candidate DOM sections
- Small HTML snippets around likely data
- Screenshot if needed
- Failed extraction result

Output:

- Revised selectors
- Revised field mapping
- Explanation of missing fields
- Confidence score

---

## 9. Page Classification

Before extraction, classify the page.

### Page types

```text
article
product_detail
product_listing
job_listing
directory_listing
table_page
search_results
company_profile
contact_page
generic_content
unknown
```

### Classification signals

Use these signals:

1. URL path
2. Page title
3. Headings
4. Visible text density
5. Number of repeated DOM blocks
6. Number of links
7. Presence of tables
8. Structured data type
9. Product/job/article schema
10. User instruction

### Example classifier output

```json
{
  "page_type": "product_listing",
  "confidence": 0.86,
  "reason": "Page contains repeated product-like cards with price text and product links.",
  "recommended_mode": "dynamic_dom_selector"
}
```

---

## 10. Intent Parsing and Schema Generation

The user's natural language instruction must be converted into a structured schema.

### Example

User says:

```text
Extract all jobs with title, company, location, salary, and apply link.
```

System generates:

```json
{
  "task_type": "list_extraction",
  "entity_name": "job",
  "fields": [
    {
      "name": "title",
      "type": "string",
      "required": true
    },
    {
      "name": "company",
      "type": "string",
      "required": false
    },
    {
      "name": "location",
      "type": "string",
      "required": false
    },
    {
      "name": "salary",
      "type": "string",
      "required": false
    },
    {
      "name": "apply_link",
      "type": "url",
      "required": false
    }
  ],
  "expected_output": "array"
}
```

### Field type options for V1

Support these basic types:

```text
string
number
integer
currency
url
email
phone
date
boolean
list[string]
```

### Required vs optional fields

By default:

- Fields explicitly requested by the user are important.
- But only mark fields as required if the instruction clearly implies they must exist.
- Missing optional fields should not fail the job.
- Too many missing important fields should trigger repair.

---

## 11. Compact Page Representation

Do not send full HTML to the model unless necessary.

Instead, create a compact representation.

### Example representation

```json
{
  "url": "https://example.com/products",
  "title": "Products - Example Store",
  "meta_description": "Shop our latest products",
  "headings": [
    "Running Shoes",
    "Best Sellers"
  ],
  "visible_text_blocks": [
    {
      "text": "Nike Runner $89.99 4.7 stars In stock",
      "selector_hint": "div.product-card:nth-child(1)"
    },
    {
      "text": "Adidas Boost $129.99 4.5 stars In stock",
      "selector_hint": "div.product-card:nth-child(2)"
    }
  ],
  "candidate_repeating_sections": [
    {
      "selector": ".product-card",
      "count": 24,
      "sample_text": "Nike Runner $89.99 4.7 stars In stock"
    }
  ],
  "tables": [],
  "structured_data_found": true,
  "links_sample": [
    {
      "text": "Nike Runner",
      "href": "/products/nike-runner"
    }
  ]
}
```

### Why compact representation matters

It reduces:

- Token cost
- Latency
- Noise
- Hallucination risk
- Model confusion

It improves:

- Selector quality
- Debuggability
- Repeatability
- Repair loop performance

---

## 12. Extraction Plan Format

The AI should return a structured extraction plan, not prose.

### Example plan

```json
{
  "strategy": "repeated_dom_selector",
  "container_selector": ".product-card",
  "fields": {
    "name": {
      "selector": ".product-title",
      "attribute": "text",
      "type": "string"
    },
    "price": {
      "selector": ".price",
      "attribute": "text",
      "type": "currency"
    },
    "rating": {
      "selector": ".rating",
      "attribute": "text",
      "type": "number"
    },
    "product_url": {
      "selector": "a",
      "attribute": "href",
      "type": "url"
    }
  },
  "pagination": {
    "has_pagination": false,
    "next_selector": null
  },
  "confidence": 0.82
}
```

### Supported V1 strategies

```text
structured_data
single_dom_selector
repeated_dom_selector
table_extraction
article_extraction
visible_text_regex
manual_fallback_failed
```

---

## 13. Extraction Execution

Execution should be deterministic.

### Do not let the AI execute arbitrary code in V1

The AI can propose selectors and extraction rules, but the backend should execute them using safe code.

### Execution rules

For each extraction plan:

1. Validate allowed strategy.
2. Validate selectors.
3. Apply selectors to DOM.
4. Extract requested attributes.
5. Normalize values.
6. Validate against schema.
7. Return result and diagnostics.

### Extracted result shape

```json
{
  "status": "success",
  "records": [
    {
      "name": "Nike Runner",
      "price": "$89.99",
      "rating": "4.7",
      "product_url": "https://example.com/products/nike-runner"
    }
  ],
  "diagnostics": {
    "strategy_used": "repeated_dom_selector",
    "records_found": 24,
    "missing_fields": {
      "rating": 2
    },
    "confidence": 0.84
  }
}
```

---

## 14. Validation and Quality Scoring

The validator decides whether extraction is good enough.

### Validation checks

1. Did the extractor return records?
2. Are requested fields present?
3. Are field types plausible?
4. Are values empty or repeated incorrectly?
5. Are URLs valid and absolute?
6. Are prices/currency values plausible?
7. Are there duplicates?
8. Does record count make sense compared with detected containers?
9. Does the output match requested shape: object vs array?
10. Are required fields mostly populated?

### Quality score example

```json
{
  "overall_score": 0.78,
  "record_count_score": 0.9,
  "field_coverage_score": 0.75,
  "type_validity_score": 0.85,
  "duplication_score": 0.95,
  "needs_repair": false
}
```

### Suggested thresholds

```text
score >= 0.80: return result
score 0.60-0.79: return result with warning, optionally run one repair attempt
score < 0.60: run repair attempt
score < 0.40 after repair: return partial result with diagnostics
```

---

## 15. Repair Loop

The repair loop is essential for making the product feel intelligent.

### When repair should trigger

Trigger repair when:

- No records found
- Too many missing important fields
- Selector matches zero elements
- Output is clearly unrelated to user instruction
- Repeated values look wrong
- Static fetch failed and dynamic rendering was not tried
- The page appears dynamic but only static mode was used

### Repair loop inputs

Send the AI:

1. Original user instruction
2. Generated schema
3. Page classification
4. Previous extraction plan
5. Previous extraction output summary
6. Validation errors
7. More detailed DOM snippets around candidate sections
8. Screenshot metadata or visual hints if available

### Repair loop output

```json
{
  "repair_action": "revise_selectors",
  "reason": "The previous container selector matched the grid wrapper, not individual product cards.",
  "new_plan": {
    "strategy": "repeated_dom_selector",
    "container_selector": "article[data-testid='product-card']",
    "fields": {
      "name": {
        "selector": "h2",
        "attribute": "text"
      },
      "price": {
        "selector": "[data-testid='price']",
        "attribute": "text"
      }
    }
  }
}
```

### V1 repair limit

Limit repair attempts to avoid runaway cost.

Recommended:

```text
max_repair_attempts = 2
```

---

## 16. Template Memory

Template memory is one of the most important V1 features.

### Why it matters

If the system successfully extracts from a site once, it should not use expensive AI planning every time.

### What to save

```json
{
  "domain": "example.com",
  "page_type": "product_listing",
  "url_pattern": "/products/*",
  "user_goal_signature": "product_name_price_rating_availability",
  "container_selector": ".product-card",
  "field_selectors": {
    "name": ".product-title",
    "price": ".price",
    "rating": ".rating",
    "availability": ".stock"
  },
  "strategy": "repeated_dom_selector",
  "success_score": 0.91,
  "created_at": "2026-05-17T00:00:00Z",
  "last_used_at": "2026-05-17T00:00:00Z"
}
```

### Template reuse process

On a new request:

1. Check domain.
2. Check URL pattern.
3. Check page type.
4. Check requested fields.
5. Try stored template.
6. Validate result.
7. If success, skip AI planning.
8. If fail, run planner and update template.

### Template states

```text
active
needs_review
deprecated
failed
```

---

## 17. API Design

### Endpoint 1: Create extraction job

```http
POST /api/extractions
```

Request:

```json
{
  "url": "https://example.com/products",
  "instruction": "Extract product names, prices, ratings, and availability",
  "output_format": "json",
  "options": {
    "use_browser": "auto",
    "max_records": 100,
    "save_template": true
  }
}
```

Response:

```json
{
  "job_id": "job_123",
  "status": "queued"
}
```

For very early MVP, this can be synchronous:

```json
{
  "status": "success",
  "records": [...],
  "diagnostics": {...}
}
```

### Endpoint 2: Get extraction result

```http
GET /api/extractions/{job_id}
```

Response:

```json
{
  "job_id": "job_123",
  "status": "success",
  "url": "https://example.com/products",
  "instruction": "Extract product names, prices, ratings, and availability",
  "records": [...],
  "diagnostics": {
    "strategy_used": "dynamic_dom_selector",
    "records_found": 24,
    "template_used": false,
    "repair_attempts": 1,
    "quality_score": 0.86
  }
}
```

### Endpoint 3: Export CSV

```http
GET /api/extractions/{job_id}/export.csv
```

### Endpoint 4: List templates

```http
GET /api/templates
```

### Endpoint 5: Re-run with saved template

```http
POST /api/templates/{template_id}/run
```

---

## 18. Database Schema - V1

### Table: extraction_jobs

```sql
CREATE TABLE extraction_jobs (
  id UUID PRIMARY KEY,
  url TEXT NOT NULL,
  domain TEXT NOT NULL,
  instruction TEXT NOT NULL,
  status TEXT NOT NULL,
  page_type TEXT,
  strategy_used TEXT,
  output_format TEXT DEFAULT 'json',
  quality_score NUMERIC,
  error_message TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### Table: extraction_results

```sql
CREATE TABLE extraction_results (
  id UUID PRIMARY KEY,
  job_id UUID REFERENCES extraction_jobs(id),
  records JSONB NOT NULL,
  diagnostics JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### Table: extraction_templates

```sql
CREATE TABLE extraction_templates (
  id UUID PRIMARY KEY,
  domain TEXT NOT NULL,
  url_pattern TEXT,
  page_type TEXT,
  goal_signature TEXT,
  strategy TEXT NOT NULL,
  extraction_plan JSONB NOT NULL,
  success_score NUMERIC,
  status TEXT DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  last_used_at TIMESTAMP
);
```

### Table: extraction_artifacts

```sql
CREATE TABLE extraction_artifacts (
  id UUID PRIMARY KEY,
  job_id UUID REFERENCES extraction_jobs(id),
  artifact_type TEXT NOT NULL,
  storage_url TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

Artifact types:

```text
raw_html
rendered_html
screenshot
compact_page_json
ai_plan_json
validation_report_json
```

---

## 19. Main Backend Modules

### Module 1: Request handler

Responsibilities:

- Accept URL and instruction
- Validate request
- Create job
- Return job id or result

### Module 2: URL normalizer

Responsibilities:

- Normalize URL
- Extract domain
- Remove tracking parameters if needed
- Resolve redirects
- Convert relative links to absolute links

### Module 3: Compliance checker

Responsibilities:

- Fetch robots.txt where applicable
- Apply rate limit policy
- Block unsupported/private schemes
- Block localhost/internal network targets unless explicitly enabled for development
- Prevent SSRF-style requests

### Module 4: Fetcher

Responsibilities:

- Static HTML fetch
- Retry basic network failures
- Detect content type
- Store raw response

### Module 5: Browser renderer

Responsibilities:

- Launch Playwright
- Navigate to page
- Wait for rendering
- Capture rendered HTML
- Capture screenshot
- Extract visible text
- Close browser safely

### Module 6: Page analyzer

Responsibilities:

- Parse HTML
- Detect structured data
- Detect tables
- Detect repeated DOM sections
- Detect article-like content
- Create compact page representation

### Module 7: AI intent parser

Responsibilities:

- Convert instruction into extraction schema
- Determine entity type
- Determine expected output shape
- Determine fields and field types

### Module 8: AI extraction planner

Responsibilities:

- Read compact page representation
- Choose extraction strategy
- Produce extraction plan
- Return confidence

### Module 9: Extraction executor

Responsibilities:

- Execute structured data extraction
- Execute selector extraction
- Execute table extraction
- Execute article extraction
- Normalize results

### Module 10: Validator

Responsibilities:

- Validate output against schema
- Compute quality score
- Identify missing fields
- Decide whether repair is needed

### Module 11: Repair manager

Responsibilities:

- Create repair prompt
- Ask AI for revised plan
- Re-run extraction
- Stop after max attempts

### Module 12: Template manager

Responsibilities:

- Save successful extraction plans
- Retrieve matching templates
- Test template success
- Mark broken templates

---

## 20. Frontend Plan

V1 frontend can be simple.

### Main screen

Fields:

1. URL input
2. Instruction text area
3. Output format dropdown
4. Max records input
5. Run button

### Result screen

Show:

1. Table preview
2. JSON preview
3. Download CSV button
4. Download JSON button
5. Diagnostics panel
6. Save template button
7. Re-run button

### Diagnostics panel

Show:

```text
Strategy used: dynamic_dom_selector
Records found: 24
Quality score: 0.86
Repair attempts: 1
Template used: no
Missing fields: rating missing for 2 records
```

### Template screen

Show saved templates:

```text
Domain
Page type
Fields
Success score
Last used
Status
```

---

## 21. AI Prompt Templates

### Prompt 1: Intent parser

System message:

```text
You convert user scraping instructions into strict JSON schemas. Do not extract data. Do not guess page content. Only infer the desired output schema from the user instruction.
```

User message:

```text
Instruction:
{{instruction}}

Return JSON with:
- task_type: list_extraction or single_entity_extraction
- entity_name
- fields: name, type, required
- expected_output: array or object
```

Expected output:

```json
{
  "task_type": "list_extraction",
  "entity_name": "product",
  "fields": [
    {
      "name": "name",
      "type": "string",
      "required": true
    }
  ],
  "expected_output": "array"
}
```

### Prompt 2: Extraction planner

System message:

```text
You are an extraction planner. You do not extract data directly. You produce safe selector-based extraction plans in JSON. Use the user's schema and compact page representation to choose the best strategy.
```

User message:

```text
User instruction:
{{instruction}}

Desired schema:
{{schema_json}}

Compact page representation:
{{compact_page_json}}

Return a JSON extraction plan with:
- strategy
- container_selector if repeated data
- fields mapping
- pagination estimate
- confidence
- reason
```

### Prompt 3: Repair planner

System message:

```text
You repair failed extraction plans. Use validation errors and page evidence to revise selectors or strategy. Return strict JSON only.
```

User message:

```text
Original instruction:
{{instruction}}

Desired schema:
{{schema_json}}

Previous plan:
{{previous_plan_json}}

Validation report:
{{validation_report_json}}

Additional page evidence:
{{additional_dom_evidence}}

Return either:
1. revised extraction plan, or
2. explanation that requested data is not present on the page.
```

---

## 22. Static vs Dynamic Detection

A major V1 decision is whether to use browser rendering.

### Start static first

Always try static fetch first because it is:

- Faster
- Cheaper
- More scalable
- Easier to debug

### Use browser if static result is insufficient

Browser should be triggered when:

```text
visible_text_length < threshold
important fields not present in static HTML
structured data not found
too many script tags and too little content
page title suggests app shell
HTTP response contains root div only
user instruction asks for visible listing but static parser finds none
```

### Example heuristic

```python
should_render = (
    visible_text_length < 1000
    or repeated_sections_count == 0
    or requested_terms_missing
    or looks_like_spa
)
```

---

## 23. Candidate Repeated Section Detection

This is one of the most important technical parts.

### Goal

Find DOM blocks that likely represent repeated records, such as product cards, jobs, restaurants, listings, or search results.

### Heuristics

Look for repeated elements with:

1. Similar DOM structure
2. Similar class names
3. Similar text shape
4. Links inside each block
5. Price/date/rating/location patterns
6. Images inside each block
7. Repeated parent container
8. Multiple sibling elements with similar children

### Candidate output

```json
[
  {
    "selector": "article.product-card",
    "count": 24,
    "average_text_length": 132,
    "sample_texts": [
      "Nike Runner $89.99 4.7 stars",
      "Adidas Boost $129.99 4.5 stars"
    ],
    "confidence": 0.89
  }
]
```

### V1 implementation shortcut

For V1, you do not need perfect generalized DOM mining.

Start with:

- common tags: `article`, `li`, `div`, `tr`
- repeated class names
- similar child structure
- minimum count: 3
- reject nav/footer/sidebar blocks
- prioritize blocks containing text matching requested fields

---

## 24. Output Normalization

Normalize common field types.

### URL

- Convert relative URLs to absolute URLs.
- Remove whitespace.
- Validate scheme is http or https.

### Currency

- Keep original text.
- Optionally parse numeric value and currency.

Example:

```json
{
  "price": "$89.99",
  "price_value": 89.99,
  "price_currency": "USD"
}
```

For V1, keep this optional.

### Text

- Trim whitespace.
- Collapse repeated spaces.
- Remove hidden text when possible.

### Dates

- Keep original date text.
- Parse normalized ISO date when confident.

### Duplicates

Deduplicate records by:

- URL if available
- name + price
- full record hash

---

## 25. Error Handling

### Error categories

```text
invalid_url
blocked_by_robots
fetch_failed
timeout
unsupported_content_type
browser_render_failed
no_relevant_data_found
schema_generation_failed
extraction_plan_failed
validation_failed
partial_success
```

### User-facing error example

```json
{
  "status": "partial_success",
  "message": "I found product names and prices, but ratings were not visible on this page.",
  "records": [...],
  "diagnostics": {
    "missing_fields": ["rating"],
    "suggestion": "Try opening a product detail page or provide a page where ratings are visible."
  }
}
```

---

## 26. Compliance and Safety Guardrails

This system should be built for legitimate web data extraction, not bypassing access controls.

### V1 guardrails

1. Respect robots.txt where applicable.
2. Do not bypass login walls.
3. Do not bypass paywalls.
4. Do not solve CAPTCHAs in V1.
5. Do not scrape private user data without permission.
6. Rate-limit requests per domain.
7. Use a clear user agent.
8. Store audit logs.
9. Block internal network URLs to prevent SSRF.
10. Block `file://`, `ftp://`, and local IP ranges by default.

### Default blocked targets

```text
localhost
127.0.0.0/8
10.0.0.0/8
172.16.0.0/12
192.168.0.0/16
169.254.0.0/16
file:// URLs
```

---

## 27. Observability

Track every extraction job.

### Logs

Log:

- URL
- domain
- page type
- strategy used
- static or browser mode
- number of records
- quality score
- repair attempts
- error category
- runtime

### Metrics

Track:

```text
extraction_success_rate
partial_success_rate
failure_rate
average_quality_score
average_latency_static
average_latency_browser
browser_usage_rate
repair_loop_rate
template_reuse_rate
cost_per_extraction
```

### Artifacts for debugging

Store:

```text
raw HTML
rendered HTML
screenshot
compact page representation
AI schema output
AI extraction plan
validation report
final result
```

---

## 28. V1 Milestones

### Milestone 1: Basic static extractor

Deliverables:

- FastAPI endpoint
- URL validation
- Static HTML fetch
- Basic DOM parsing
- Manual extraction plan execution
- JSON output

Acceptance criteria:

- Can extract from simple static pages using a hardcoded plan.

### Milestone 2: Intent parser

Deliverables:

- AI converts instruction into schema
- Schema validation with Pydantic
- Supports list and single-object extraction

Acceptance criteria:

- Given 20 sample prompts, system generates reasonable schemas for at least 16.

### Milestone 3: Compact page analyzer

Deliverables:

- Extract title/headings/visible text
- Detect tables
- Detect structured data
- Detect repeated DOM candidates
- Create compact page JSON

Acceptance criteria:

- For sample product/job/listing pages, candidate repeated sections are detected.

### Milestone 4: AI extraction planner

Deliverables:

- AI receives schema + compact page JSON
- AI returns structured extraction plan
- Plan executor applies selectors

Acceptance criteria:

- Can extract basic product/job/listing data from static pages.

### Milestone 5: Playwright dynamic rendering

Deliverables:

- Browser rendering fallback
- Screenshot capture
- Rendered DOM extraction
- Timeout handling

Acceptance criteria:

- Can extract from JavaScript-rendered sample pages.

### Milestone 6: Validator and repair loop

Deliverables:

- Quality scoring
- Missing field detection
- One to two repair attempts
- Partial success response

Acceptance criteria:

- On failed selectors, system retries with improved plan.

### Milestone 7: Template memory

Deliverables:

- Save successful extraction templates
- Reuse templates by domain/page type
- Mark failed templates

Acceptance criteria:

- Second extraction from same page type avoids AI planning if template still works.

### Milestone 8: UI and export

Deliverables:

- URL + instruction UI
- Table preview
- JSON preview
- CSV download
- Diagnostics panel

Acceptance criteria:

- Non-technical user can run extraction and download results.

---

## 29. Suggested Timeline

Assuming one full-stack developer or a small team.

### Week 1

- FastAPI project setup
- Static fetcher
- DOM parser
- Basic endpoint
- Simple result object
- Store raw HTML

### Week 2

- Intent parser
- Pydantic schema generation
- Compact page representation
- Structured data extraction
- Table extraction

### Week 3

- Repeated section detection
- AI extraction planner
- Selector executor
- Output normalization
- Initial validation

### Week 4

- Playwright rendering fallback
- Screenshots
- Dynamic DOM extraction
- Better page classification

### Week 5

- Repair loop
- Quality scoring
- Template storage and reuse
- Error handling improvements

### Week 6

- Basic frontend
- CSV/JSON export
- Diagnostics panel
- Test suite
- Demo scenarios

A realistic V1 prototype can be done in 4 to 6 weeks if the scope stays tight.

---

## 30. Testing Plan

### Test page categories

Create a test set with:

1. Static product listing
2. Dynamic product listing
3. Product detail page
4. Static article page
5. JavaScript-rendered article page
6. HTML table page
7. Job listing page
8. Directory/contact page
9. Page with no requested data
10. Page with partial requested data

### Test prompts

Examples:

```text
Extract all product names and prices.
Extract product name, price, rating, and product URL.
Extract all jobs with title, company, location, and apply link.
Extract the table as CSV.
Extract article title, author, publish date, and main content.
Extract company name, phone number, email, and address.
```

### Evaluation metrics

For each test:

```text
record_count_accuracy
field_accuracy
missing_field_rate
false_positive_rate
runtime
repair_attempt_count
template_reuse_success
```

### Manual review

For V1, include manual review of outputs. Automated evaluation is useful, but scraping quality often requires human inspection.

---

## 31. Demo Scenarios

Prepare 5 high-quality demos.

### Demo 1: Product listing

Input:

```text
Extract product name, price, rating, and product URL.
```

Expected output:

- JSON array
- CSV export
- Diagnostics showing repeated card strategy

### Demo 2: Job board

Input:

```text
Extract job title, company, location, salary, and apply link.
```

Expected output:

- List of jobs
- Missing salary handled gracefully if salary is not visible

### Demo 3: Article page

Input:

```text
Extract title, author, publish date, and article text.
```

Expected output:

- Single object
- Clean article text

### Demo 4: Table page

Input:

```text
Extract this table and return CSV.
```

Expected output:

- Table preview
- CSV download

### Demo 5: Template reuse

Input:

```text
Run the same product extractor on another category page from the same website.
```

Expected output:

- Template used
- Faster runtime
- Lower AI cost

---

## 32. Risks and Mitigations

### Risk 1: AI generates bad selectors

Mitigation:

- Use compact page representation
- Provide candidate sections
- Validate selectors before execution
- Use repair loop
- Save successful templates

### Risk 2: Dynamic pages are slow

Mitigation:

- Static-first strategy
- Browser only when needed
- Browser timeout
- Reuse browser contexts
- Queue browser jobs

### Risk 3: Cost gets high

Mitigation:

- Do not send full HTML
- Cache page analysis
- Reuse templates
- Use AI only for planning and repair
- Add local model later

### Risk 4: Sites change layout

Mitigation:

- Quality validation
- Template health status
- Auto-repair templates
- Store old and new plans

### Risk 5: Legal/compliance problems

Mitigation:

- Respect robots.txt where applicable
- No paywall/login/CAPTCHA bypass
- Rate limits
- Clear user agent
- Audit logs

### Risk 6: User instruction is vague

Mitigation:

- Make best effort
- Infer likely schema
- Return diagnostics
- In UI, allow user to edit columns before final export

---

## 33. Success Criteria for V1

V1 is successful if:

1. A user can paste a URL and instruction and get structured data.
2. The system works on both static and dynamic pages.
3. The output is useful without writing selectors manually.
4. The system can explain what strategy it used.
5. The system handles partial success gracefully.
6. Successful extraction plans can be reused.
7. The product is demoable with 5 strong examples.

### Target V1 metrics

```text
Static page success rate: 80%+
Dynamic page success rate: 60%+
Template reuse success rate: 80%+
Average static extraction latency: under 5 seconds
Average dynamic extraction latency: under 20 seconds
Repair loop improves failed extraction in at least 30% of failed cases
```

These are initial product targets, not guaranteed benchmarks.

---

## 34. Recommended Implementation Order

Build in this order:

1. URL validation and static fetcher
2. Basic HTML parser
3. Intent-to-schema AI prompt
4. Compact page representation
5. Repeated section detection
6. AI extraction planner
7. Selector executor
8. Validator
9. Playwright fallback
10. Repair loop
11. Template memory
12. CSV export
13. Basic UI
14. Diagnostics and logs
15. Test suite

Avoid starting with:

- Proxies
- Anti-bot systems
- Complex crawling
- Scheduling
- Enterprise account management
- Browser infrastructure optimization

Those can come later.

---

## 35. V1 Repository Structure

Suggested structure:

```text
ai-web-extractor/
  backend/
    app/
      main.py
      api/
        routes_extractions.py
        routes_templates.py
      core/
        config.py
        security.py
        logging.py
      models/
        extraction_job.py
        extraction_template.py
      schemas/
        requests.py
        responses.py
        extraction_schema.py
      services/
        url_normalizer.py
        compliance_checker.py
        static_fetcher.py
        browser_renderer.py
        page_analyzer.py
        intent_parser.py
        extraction_planner.py
        extraction_executor.py
        validator.py
        repair_manager.py
        template_manager.py
        exporter.py
      prompts/
        intent_parser.md
        extraction_planner.md
        repair_planner.md
      tests/
        test_intent_parser.py
        test_page_analyzer.py
        test_extraction_executor.py
        test_validator.py
    pyproject.toml
  frontend/
    app/
      page.tsx
      extraction/[id]/page.tsx
    components/
      UrlInstructionForm.tsx
      ResultTable.tsx
      JsonViewer.tsx
      DiagnosticsPanel.tsx
    package.json
  docs/
    architecture.md
    api.md
    testing.md
  README.md
```

---

## 36. Minimal V1 Backend Pseudocode

```python
async def run_extraction(url: str, instruction: str):
    normalized_url = normalize_url(url)
    check_url_is_safe(normalized_url)
    check_compliance(normalized_url)

    schema = await intent_parser.parse(instruction)

    template = template_manager.find_matching_template(
        url=normalized_url,
        schema=schema,
    )

    static_page = await static_fetcher.fetch(normalized_url)
    static_analysis = page_analyzer.analyze(static_page.html, normalized_url)

    if template:
        result = extraction_executor.execute(
            plan=template.extraction_plan,
            html=static_page.html,
            schema=schema,
            base_url=normalized_url,
        )
        validation = validator.validate(result, schema)
        if validation.good_enough:
            return format_success(result, validation, template_used=True)

    if static_analysis.is_sufficient_for_instruction(schema):
        compact_page = static_analysis.compact_representation
    else:
        rendered_page = await browser_renderer.render(normalized_url)
        compact_page = page_analyzer.analyze(
            rendered_page.html,
            normalized_url,
            screenshot=rendered_page.screenshot_path,
        ).compact_representation

    plan = await extraction_planner.plan(
        instruction=instruction,
        schema=schema,
        compact_page=compact_page,
    )

    result = extraction_executor.execute(
        plan=plan,
        html=compact_page.source_html,
        schema=schema,
        base_url=normalized_url,
    )

    validation = validator.validate(result, schema)

    repair_attempts = 0
    while validation.needs_repair and repair_attempts < 2:
        repaired_plan = await repair_manager.repair(
            instruction=instruction,
            schema=schema,
            previous_plan=plan,
            validation=validation,
            compact_page=compact_page,
        )
        result = extraction_executor.execute(
            plan=repaired_plan,
            html=compact_page.source_html,
            schema=schema,
            base_url=normalized_url,
        )
        validation = validator.validate(result, schema)
        plan = repaired_plan
        repair_attempts += 1

    if validation.good_enough:
        template_manager.save_successful_template(
            url=normalized_url,
            schema=schema,
            plan=plan,
            score=validation.quality_score,
        )

    return format_result(result, validation, repair_attempts)
```

---

## 37. Final Recommendation

For Version 1, build a focused product around this loop:

```text
URL + instruction
-> intent schema
-> static fetch
-> page analysis
-> browser fallback if needed
-> AI extraction plan
-> deterministic execution
-> validation
-> repair
-> reusable template
-> JSON/CSV output
```

Do not build a general crawler first. Do not start with proxy infrastructure. Do not over-invest in anti-bot handling. The first product risk is not crawling scale; it is whether the intelligent planner can reliably understand what the human wants and extract it from common page structures.

The strongest V1 differentiator is:

> A small AI planner that understands human data intent and turns it into reliable extraction rules, while proven scraping tools do the actual work.

---

## 38. References

These references are useful for the underlying tool choices and compliance model:

- Playwright documentation: https://playwright.dev/docs/api/class-playwright
- Crawlee Playwright crawler documentation: https://crawlee.dev/js/docs/examples/playwright-crawler
- Scrapy documentation: https://docs.scrapy.org/en/latest/index.html
- Trafilatura documentation: https://trafilatura.readthedocs.io/
- Firecrawl scrape endpoint documentation: https://docs.firecrawl.dev/api-reference/endpoint/scrape
- Zyte API overview: https://www.zyte.com/zyte-api/
- Browserless overview: https://www.browserless.io/
- Robots Exclusion Protocol RFC 9309: https://www.rfc-editor.org/rfc/rfc9309.html
