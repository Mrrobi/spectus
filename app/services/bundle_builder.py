from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from selectolax.parser import HTMLParser, Node

from app.schemas.bundle import AnchorEntry, FactsBundle, KVPair
from app.services import structured_data

_WS_RE = re.compile(r"\s+")
_NON_VISIBLE = frozenset({"script", "style", "noscript", "head", "meta", "link", "template"})
_LABEL_NEAR_VALUE_RE = re.compile(
    r"([A-ZÆØÅa-zæøå][A-ZÆØÅa-zæøå ./()\-]{2,40}?)\s*[: \-]?\s*"
    r"((?:[+€$£¥kr]|\d|[A-Z0-9]).{1,120}?)(?=\n|$|  )",
    re.MULTILINE,
)
_PRICE_NEARBY_RE = re.compile(r"([\d\s ]{4,15})\s*kr\b", re.IGNORECASE)

_CALENDAR_HOSTS = (".ics", "calendar", "ical")


def _text(node: Node) -> str:
    return _WS_RE.sub(" ", node.text(separator=" ", strip=True))


def _collect_anchors(tree: HTMLParser, base_url: str, cap: int = 80) -> list[AnchorEntry]:
    out: list[AnchorEntry] = []
    seen: set[str] = set()
    for a in tree.css("a[href]"):
        if len(out) >= cap:
            break
        text = _text(a)[:140]
        raw_href = (a.attributes.get("href") or "").strip()
        if not raw_href or raw_href.startswith("#") or raw_href.lower().startswith("javascript:"):
            continue
        try:
            href = urljoin(base_url, raw_href)
        except (ValueError, TypeError):
            continue
        key = f"{text}|{href}"
        if key in seen:
            continue
        seen.add(key)
        out.append(AnchorEntry(text=text or "", href=href))
    return out


def _collect_kv_from_dl(tree: HTMLParser) -> list[KVPair]:
    out: list[KVPair] = []
    for dl in tree.css("dl"):
        dts = dl.css("dt")
        dds = dl.css("dd")
        for dt, dd in zip(dts, dds):
            label = _text(dt)[:120]
            value = _text(dd)[:300]
            if label and value:
                out.append(KVPair(label=label, value=value))
    return out


def _collect_kv_from_table(tree: HTMLParser) -> list[KVPair]:
    out: list[KVPair] = []
    for table in tree.css("table"):
        for row in table.css("tr"):
            cells = row.css("th, td")
            if len(cells) != 2:
                continue
            label = _text(cells[0])[:120]
            value = _text(cells[1])[:300]
            if label and value:
                out.append(KVPair(label=label, value=value))
    return out


def _collect_kv_from_pairs(tree: HTMLParser) -> list[KVPair]:
    """Heuristic: <span class="label">X</span><span>Y</span> patterns."""
    out: list[KVPair] = []
    for el in tree.css("[class*='label'], [class*='Label'], [class*='key']"):
        text = _text(el)[:120]
        if not text or len(text) > 80:
            continue
        nxt = el.next
        # selectolax Node.next iterates over text nodes too; skip empty
        depth = 0
        while nxt is not None and depth < 5:
            if hasattr(nxt, "tag") and nxt.tag:
                value = _text(nxt)[:300]
                if value and len(value) <= 280:
                    out.append(KVPair(label=text, value=value))
                    break
            nxt = nxt.next if hasattr(nxt, "next") else None
            depth += 1
    return out


def _collect_text_blocks(tree: HTMLParser, cap: int = 40) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for selector in ("h1", "h2", "h3", "h4", "p", "li", "section", "article", "blockquote"):
        for node in tree.css(selector):
            if node.tag in _NON_VISIBLE:
                continue
            t = _text(node)
            if not t or len(t) < 8 or len(t) > 600:
                continue
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= cap:
                return out
    return out


def _collect_headings(tree: HTMLParser, cap: int = 25) -> list[str]:
    out: list[str] = []
    for tag in ("h1", "h2", "h3"):
        for n in tree.css(tag):
            t = _text(n)[:150]
            if t and t not in out:
                out.append(t)
            if len(out) >= cap:
                return out
    return out


def _collect_calendar_urls(anchors: list[AnchorEntry]) -> list[str]:
    out: list[str] = []
    for a in anchors:
        href = a.href.lower()
        if any(h in href for h in _CALENDAR_HOSTS):
            out.append(a.href)
        elif "icalendarfrom=" in href or "ical=" in href:
            out.append(a.href)
    return out[:5]


def _structured_data_compact(html: str, max_chars: int = 6000) -> str:
    sd = structured_data.extract(html)
    payload = {
        "json_ld_types": sd.json_ld_types,
        "open_graph": dict(list(sd.open_graph.items())[:20]),
        "twitter": dict(list(sd.twitter.items())[:10]),
        "microdata_types": sd.microdata_types,
        "next_data_present": sd.next_data_present,
        "nuxt_data_present": sd.nuxt_data_present,
        "initial_state_present": sd.initial_state_present,
        "raw_payloads": [p.model_dump() for p in sd.raw_payloads[:5]],
    }
    text = json.dumps(payload, ensure_ascii=False)
    return text[:max_chars]


def build_facts_bundle(html: str, base_url: str) -> FactsBundle:
    if not html:
        return FactsBundle(url=base_url)
    tree = HTMLParser(html)
    title = None
    if tree.css_first("title"):
        title = _text(tree.css_first("title"))[:300]
    meta = tree.css_first('meta[name="description"]')
    meta_desc = None
    if meta:
        v = meta.attributes.get("content")
        if v:
            meta_desc = _WS_RE.sub(" ", v).strip()[:500]
    headings = _collect_headings(tree)
    anchors = _collect_anchors(tree, base_url)
    calendar_urls = _collect_calendar_urls(anchors)
    kvs = _collect_kv_from_dl(tree)
    kvs.extend(_collect_kv_from_table(tree))
    if len(kvs) < 30:
        kvs.extend(_collect_kv_from_pairs(tree))
    # Dedup KV by label
    seen_labels: set[str] = set()
    deduped_kvs: list[KVPair] = []
    for kv in kvs:
        if kv.label.lower() in seen_labels:
            continue
        seen_labels.add(kv.label.lower())
        deduped_kvs.append(kv)
        if len(deduped_kvs) >= 40:
            break
    text_blocks = _collect_text_blocks(tree)
    sd_compact = _structured_data_compact(html)
    return FactsBundle(
        url=base_url,
        title=title,
        meta_description=meta_desc,
        structured_data_compact=sd_compact,
        anchors=anchors,
        key_value_pairs=deduped_kvs,
        text_blocks=text_blocks,
        headings=headings,
        calendar_urls=calendar_urls,
    )
