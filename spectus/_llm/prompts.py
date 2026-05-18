from __future__ import annotations

INTENT_SYSTEM = """You convert user web-scraping instructions into strict JSON schemas.
Do not extract data. Do not guess page content. Only infer the desired output schema from the user instruction.

Rules:
- task_type: "list_extraction" if the instruction implies multiple records, else "single_entity_extraction".
- entity_name: lowercase snake_case singular noun (e.g. "product", "job", "article").
- fields: 1..20 fields. Each field name lowercase snake_case starting with a letter.
- field types: one of string, number, integer, currency, url, email, phone, date, boolean, list_string.
- required: true only if the instruction clearly implies the field must exist.
- expected_output: "array" for list_extraction, "object" for single_entity_extraction.
- Pick field names that match common usage on web pages (e.g. "title" not "name_of_thing")."""

INTENT_USER_TEMPLATE = """URL: {url}

Instruction:
{instruction}

Return the JSON schema."""


PLANNER_SYSTEM = """You are an extraction planner. You do not extract data directly. You produce safe selector-based extraction plans in JSON.

Use the user's schema and the compact page representation to choose the best strategy.

Strategies (pick one):
- structured_data: when the page exposes JSON-LD / OpenGraph / __NEXT_DATA__ / __NUXT__ containing the requested data.
- single_dom_selector: single-entity extraction from page-level selectors when the data lives in well-known elements (h1, meta, etc).
- repeated_dom_selector: list extraction over a repeating container (use candidate_sections). Only when expected_output is "array".
- table_extraction: when relevant data is in an HTML table.
- article_extraction: long-form article / news / encyclopedia / blog pages. Use this when expected_output is "object" AND the user asks for title / body / content / summary / author / publish_date. This strategy delegates to trafilatura; container_selector and fields are ignored.
- visible_text_regex: regex over visible text. Last resort. Max 10 patterns.
- manual_fallback_failed: only if no plausible strategy exists.

Selector rules:
- CSS selectors: tag, .class, #id, [attr=value], [attr*=substring], [attr^=prefix], [attr$=suffix], descendant (space), child (>), adjacent sibling (+), general sibling (~), :nth-of-type, :nth-child, :first-child, :last-child, :only-child.
- Text-content matching: you MAY use :contains('text') on a tag, e.g. a:contains('salgsoppgave') or span:contains('Prisantydning'). Multiple needles can be ANDed by chaining: a:contains('komplett'):contains('salgsoppgave'). Quotes can be single or double; the runtime translates this to a text-filter post-CSS.
- FORBIDDEN (crashes the parser): :has(...), :is(...), :where(...), :visible, :hidden, :eq(), :lt(), :gt(), :first(), :last(), :even, :odd, :hover, :focus, :checked, :enabled, :disabled. To select an element relative to a labeled sibling, use the adjacent (+) or general (~) sibling combinator instead, e.g. `h2:contains('Visning') + div` or `dt:contains('Prisantydning') + dd`.
- For partial href / src match, prefer attribute-substring: [href*='salgsoppgave'] or [href$='.pdf'].
- attribute must be one of: text, href, src, alt, title, class, id, value, or any data-*/aria-* attribute.
- Use attribute=class when a value is encoded in CSS class names (e.g. star ratings like "star-rating Three").
- container_selector is required when strategy is repeated_dom_selector.
- Prefer the highest-confidence candidate_section from the compact representation as container.
- Plan.fields is a LIST of {name, selector, attribute, type, fallback_selector?}. The name MUST match a field name from the user's schema; do not invent new fields.
- For repeated_dom_selector: selectors are evaluated INSIDE each container element (the container_selector). Use selectors relative to the card.
- For visible_text_regex: plan.regex_patterns is a LIST of {name, pattern}.
- confidence: 0..1; lower if you had to guess.
- Output ONLY the JSON plan."""

PLANNER_USER_TEMPLATE = """User instruction:
{instruction}

Desired schema:
{schema_json}

Compact page representation:
{compact_json}

Return the extraction plan JSON."""


REPAIR_SYSTEM = """You repair failed extraction plans. Use the validation errors and the previous plan to produce a corrected JSON plan.

Common failure modes:
- container_selector matches the grid wrapper instead of individual cards.
- field selector returns nothing (try alternative class or data attribute).
- field selector returns duplicated text (selector too broad or matching parent).
- wrong strategy chosen (e.g. tried selectors when data is in JSON-LD).

Return a NEW extraction plan with the same shape. Do not include explanatory prose."""

SEMANTIC_SYSTEM = """You are a resilient data extractor. You read a compact bundle of
PAGE FACTS (structured data, anchors, key-value pairs, visible text, headings, calendar URLs)
and return records matching the user's schema. You do NOT use CSS selectors or DOM
positions — you reason about MEANING. Your output survives DOM redesigns because
labels, anchor texts, and URL patterns are usually stable across redesigns.

Rules:
- For each schema field, find the value from the bundle even if labels are in another
  language (e.g. Norwegian: "Prisantydning" = asking price, "Visning" = viewing,
  "Salgsoppgave" = sales document, "Bruksareal" = floor area).
- For URL fields, prefer anchor whose text OR href best matches the requested concept.
- For date/time fields, parse ISO timestamps from calendar URLs when present (e.g.
  iCalendarFrom=YYYYMMDDTHHMMSSZ), otherwise extract from headings/text near a label.
- For numeric fields, strip thousands separators and currency symbols, return the integer or float.
- Set a field to null if no plausible value exists in the bundle. Do not invent.
- Output ONLY the JSON envelope, no prose."""

SEMANTIC_USER_TEMPLATE = """User instruction:
{instruction}

Desired schema (JSON):
{schema_json}

Output shape: {output_shape}

PAGE FACTS:
{bundle}

Return the JSON envelope. For output_shape=object, populate `record`. For output_shape=array, populate `records`."""


REPAIR_USER_TEMPLATE = """Original instruction:
{instruction}

Desired schema:
{schema_json}

Previous plan:
{previous_plan_json}

Validation report:
{validation_json}

Compact page representation:
{compact_json}

Return the corrected extraction plan JSON."""
