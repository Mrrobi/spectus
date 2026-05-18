from __future__ import annotations

import re
from urllib.parse import urljoin

from selectolax.parser import HTMLParser, Node

from spectus.config import Settings
from spectus._schemas.intent import IntentSchema
from spectus._schemas.page import (
    CompactPage,
    LinkSample,
    StructuredDataSummary,
    TableSummary,
)
from spectus._core import structured_data
from spectus._core.repeated_detector import detect_repeated_sections

_NON_VISIBLE_TAGS = frozenset({"script", "style", "noscript", "head", "meta", "link", "template"})
_WS_RE = re.compile(r"\s+")
_NAV_TAGS = frozenset({"nav", "footer", "aside", "header"})


def _text_metrics(tree: HTMLParser) -> tuple[int, float]:
    body = tree.body or tree.root
    if body is None:
        return 0, 0.0
    visible_chars = 0
    for node in body.iter(include_text=False):
        if node.tag in _NON_VISIBLE_TAGS:
            continue
    text = ""
    if body is not None:
        text = body.text(separator=" ", strip=True) or ""
    text = _WS_RE.sub(" ", text)
    visible_chars = len(text)
    total = len(tree.html or "") or 1
    return visible_chars, visible_chars / total


def _summarize_tables(tree: HTMLParser, base_url: str) -> list[TableSummary]:
    out: list[TableSummary] = []
    for idx, table in enumerate(tree.css("table")):
        if idx >= 5:
            break
        rows = table.css("tr")
        if not rows:
            continue
        header_cells = rows[0].css("th") or rows[0].css("td")
        headers = [_WS_RE.sub(" ", c.text(strip=True))[:100] for c in header_cells][:30]
        body_rows = rows[1:] if rows[0].css("th") else rows
        sample_rows: list[list[str]] = []
        for r in body_rows[:2]:
            cells = r.css("td") or r.css("th")
            sample_rows.append([_WS_RE.sub(" ", c.text(strip=True))[:100] for c in cells][:30])
        col_count = max((len(r.css("td") or r.css("th")) for r in body_rows[:5]), default=0)
        out.append(
            TableSummary(
                selector=f"table:nth-of-type({idx + 1})",
                row_count=len(body_rows),
                col_count=col_count,
                headers=headers,
                sample_rows=sample_rows,
            )
        )
    return out


def _sample_links(tree: HTMLParser, base_url: str) -> list[LinkSample]:
    out: list[LinkSample] = []
    for a in tree.css("a[href]"):
        if len(out) >= 20:
            break
        if _is_in_nav(a):
            continue
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        try:
            absolute = urljoin(base_url, href)
        except (ValueError, TypeError):
            continue
        text = _WS_RE.sub(" ", a.text(strip=True))[:120]
        out.append(LinkSample(text=text, href=absolute))
    return out


def _is_in_nav(node: Node) -> bool:
    cur = node.parent
    depth = 0
    while cur is not None and depth < 30:
        if cur.tag in _NAV_TAGS:
            return True
        cur = cur.parent
        depth += 1
    return False


def _classify_heuristic(
    headings: list[str],
    candidates: list,
    tables: list[TableSummary],
    structured: StructuredDataSummary,
    visible_text_length: int,
) -> str:
    types_lower = {t.lower() for t in structured.json_ld_types}
    md_lower = {t.lower() for t in structured.microdata_types}
    if "article" in types_lower or "newsarticle" in types_lower or "article" in md_lower:
        return "article"
    if "product" in types_lower or "product" in md_lower:
        if candidates and candidates[0].count >= 3:
            return "product_listing"
        return "product_detail"
    if "jobposting" in types_lower:
        return "job_listing"
    if tables and tables[0].row_count > 5:
        return "table_page"
    if candidates and candidates[0].count >= 5:
        return "directory_listing"
    if candidates and candidates[0].count >= 3:
        return "search_results"
    if visible_text_length > 3000 and not candidates:
        return "article"
    return "generic_content"


class PageAnalyzer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def analyze(self, html: str, base_url: str) -> CompactPage:
        if not html:
            return CompactPage(url=base_url)
        tree = HTMLParser(html)
        title_node = tree.css_first("title")
        title = _WS_RE.sub(" ", title_node.text(strip=True))[:300] if title_node else None
        meta_desc_node = tree.css_first('meta[name="description"]')
        meta_desc = None
        if meta_desc_node:
            v = meta_desc_node.attributes.get("content")
            if v:
                meta_desc = _WS_RE.sub(" ", v).strip()[:500]
        headings = []
        for tag in ("h1", "h2", "h3"):
            for h in tree.css(tag):
                if len(headings) >= 30:
                    break
                t = _WS_RE.sub(" ", h.text(strip=True))[:120]
                if t:
                    headings.append(t)
            if len(headings) >= 30:
                break
        visible_text_length, ratio = _text_metrics(tree)
        structured = structured_data.extract(html)
        tables = _summarize_tables(tree, base_url)
        candidates = detect_repeated_sections(html)
        links = _sample_links(tree, base_url)
        page_type_hint = _classify_heuristic(
            headings, candidates, tables, structured, visible_text_length
        )
        return CompactPage(
            url=base_url,
            title=title,
            meta_description=meta_desc,
            headings=headings,
            visible_text_length=visible_text_length,
            text_to_markup_ratio=ratio,
            candidate_sections=candidates,
            tables=tables,
            structured_data=structured,
            links_sample=links,
            page_type_hint=page_type_hint,
        )

    def is_sufficient_for(self, page: CompactPage, schema: IntentSchema) -> bool:
        if page.visible_text_length < 1000:
            return False
        if (
            schema.expected_output == "array"
            and not page.candidate_sections
            and not page.tables
        ):
            return False
        if (
            page.text_to_markup_ratio < 0.05
            and page.structured_data.next_data_present
        ):
            return False
        if schema.expected_output == "array":
            text_blob = " ".join(page.headings).lower()
            if page.candidate_sections:
                text_blob += " " + " ".join(
                    " ".join(c.sample_texts) for c in page.candidate_sections
                ).lower()
            if not any(_field_term(f.name) in text_blob for f in schema.required_fields()):
                if not page.structured_data.json_ld_types:
                    return False
        return True


def _field_term(name: str) -> str:
    return name.replace("_", " ")
