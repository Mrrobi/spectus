from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import regex
from selectolax.parser import HTMLParser, Node

from spectus.config import Settings
from spectus.errors import InvalidSelectorError
from spectus.logging import get_logger
from spectus._schemas.execution import ExtractionResult, FieldStat
from spectus._schemas.intent import IntentSchema
from spectus._schemas.plan import ExtractionPlan, FieldSelector
from spectus._core.normalizer import FieldNormalizer

_MAX_ELEMENTS_PER_SELECTOR = 500
_WS_RE = re.compile(r"\s+")
_REGEX_TIMEOUT_S = 0.05

_UNSUPPORTED_SELECTOR_RE = re.compile(
    r":(has|is|where|matches|visible|hidden|eq|lt|gt|first|last|even|odd|"
    r"hover|focus|target|enabled|disabled|checked)\b",
    re.IGNORECASE,
)
_CONTAINS_RE = re.compile(r":contains\(\s*(['\"])(?P<text>(?:\\.|[^\\])*?)\1\s*\)")


def is_safe_selector(selector: str | None) -> bool:
    if not selector:
        return False
    if len(selector) > 500:
        return False
    if _UNSUPPORTED_SELECTOR_RE.search(selector):
        return False
    return True


def _split_compound(selector: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    in_quote: str | None = None
    for ch in selector:
        if in_quote:
            cur.append(ch)
            if ch == in_quote:
                in_quote = None
            continue
        if ch in "\"'":
            in_quote = ch
            cur.append(ch)
            continue
        if ch in "([":
            depth += 1
            cur.append(ch)
            continue
        if ch in ")]":
            depth -= 1
            cur.append(ch)
            continue
        if ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


def _resolve_selector(root: "Node", selector: str) -> list["Node"]:
    """CSS query with translation for jQuery `:contains('text')`.

    `:has(...)`, `:is(...)`, etc remain rejected (lexbor cannot parse).
    """
    if not selector:
        return []
    out: list[Node] = []
    seen: set[int] = set()
    for clause in _split_compound(selector):
        if not clause:
            continue
        if _UNSUPPORTED_SELECTOR_RE.search(clause):
            continue
        matches = list(_CONTAINS_RE.finditer(clause))
        if matches:
            base = _CONTAINS_RE.sub("", clause).strip() or "*"
            if _UNSUPPORTED_SELECTOR_RE.search(base):
                continue
            try:
                nodes = root.css(base)
            except Exception:
                continue
            needles = [m.group("text") for m in matches]
            scored: list[tuple[int, Node]] = []
            for n in nodes:
                text = _WS_RE.sub(" ", n.text(separator=" ", strip=True))
                if all(needle in text for needle in needles):
                    scored.append((len(text), n))
            scored.sort(key=lambda kv: kv[0])
            for _, n in scored:
                key = id(n.html) if hasattr(n, "html") else id(n)
                if key not in seen:
                    seen.add(key)
                    out.append(n)
        else:
            try:
                nodes = root.css(clause)
            except Exception:
                continue
            for n in nodes:
                out.append(n)
        if len(out) >= _MAX_ELEMENTS_PER_SELECTOR:
            break
    return out[:_MAX_ELEMENTS_PER_SELECTOR]


def _resolve_selector_first(root: "Node", selector: str) -> "Node | None":
    nodes = _resolve_selector(root, selector)
    return nodes[0] if nodes else None


class ExtractionExecutor:
    def __init__(self, normalizer: FieldNormalizer, settings: Settings) -> None:
        self._normalizer = normalizer
        self._settings = settings
        self._log = get_logger("executor")

    def execute(
        self,
        plan: ExtractionPlan,
        html: str,
        base_url: str,
        schema: IntentSchema,
        max_records: int,
    ) -> ExtractionResult:
        cap = min(max_records, self._settings.max_records_hard_cap)
        if len(html.encode("utf-8", errors="ignore")) > self._settings.max_html_bytes:
            self._log.warning("html_oversized", bytes=len(html))
            html = html[: self._settings.max_html_bytes]
        tree = HTMLParser(html)
        match plan.strategy:
            case "structured_data":
                return self._exec_structured(plan, html, base_url, schema, cap)
            case "single_dom_selector":
                return self._exec_single(plan, tree, base_url, schema)
            case "repeated_dom_selector":
                return self._exec_repeated(plan, tree, base_url, schema, cap)
            case "table_extraction":
                return self._exec_table(plan, tree, base_url, schema, cap)
            case "article_extraction":
                return self._exec_article(plan, html, base_url, schema)
            case "visible_text_regex":
                return self._exec_regex(plan, tree, base_url, schema, cap)
            case "manual_fallback_failed":
                return ExtractionResult(
                    status="empty",
                    strategy_used=plan.strategy,
                    records=[],
                    notes=["planner indicated manual fallback required"],
                )

    def _exec_single(
        self,
        plan: ExtractionPlan,
        tree: HTMLParser,
        base_url: str,
        schema: IntentSchema,
    ) -> ExtractionResult:
        field_map = plan.field_map()
        record, stats = self._extract_fields_from_root(tree.root, field_map, base_url, schema)
        return ExtractionResult(
            status="success" if record else "empty",
            strategy_used="single_dom_selector",
            records=[record] if record else [],
            field_diagnostics=stats,
        )

    def _exec_repeated(
        self,
        plan: ExtractionPlan,
        tree: HTMLParser,
        base_url: str,
        schema: IntentSchema,
        cap: int,
    ) -> ExtractionResult:
        if not plan.container_selector:
            return ExtractionResult(
                status="empty",
                strategy_used="repeated_dom_selector",
                records=[],
                notes=["missing container_selector"],
            )
        containers = self._safe_css(tree.root, plan.container_selector)
        if not containers:
            return ExtractionResult(
                status="empty",
                strategy_used="repeated_dom_selector",
                records=[],
                notes=["container_selector matched 0 elements"],
            )
        records: list[dict[str, Any]] = []
        stats: dict[str, FieldStat] = {}
        field_map = plan.field_map()
        for container in containers[:cap]:
            record, sub_stats = self._extract_fields_from_root(
                container, field_map, base_url, schema
            )
            if record:
                records.append(record)
            for k, v in sub_stats.items():
                if k not in stats:
                    stats[k] = FieldStat(hits=v.hits, misses=v.misses, errors=v.errors)
                else:
                    cur = stats[k]
                    stats[k] = FieldStat(
                        hits=cur.hits + v.hits,
                        misses=cur.misses + v.misses,
                        errors=cur.errors + v.errors,
                    )
        return ExtractionResult(
            status="success" if records else "empty",
            strategy_used="repeated_dom_selector",
            records=records,
            field_diagnostics=stats,
        )

    def _exec_table(
        self,
        plan: ExtractionPlan,
        tree: HTMLParser,
        base_url: str,
        schema: IntentSchema,
        cap: int,
    ) -> ExtractionResult:
        table_selector = plan.table_selector or "table"
        table = self._safe_css_first(tree.root, table_selector)
        if table is None:
            return ExtractionResult(
                status="empty",
                strategy_used="table_extraction",
                records=[],
                notes=[f"no table matched selector '{table_selector}'"],
            )
        rows = table.css("tr")
        if not rows:
            return ExtractionResult(
                status="empty",
                strategy_used="table_extraction",
                records=[],
                notes=["table has no rows"],
            )
        header_cells = rows[0].css("th") or rows[0].css("td")
        headers = [_WS_RE.sub(" ", c.text(strip=True)).lower() for c in header_cells]
        body_rows = rows[1:] if rows[0].css("th") else rows
        field_map = {f.name: _match_header_to_field(f.name, headers) for f in schema.fields}
        records: list[dict[str, Any]] = []
        stats: dict[str, FieldStat] = {f.name: FieldStat() for f in schema.fields}
        for r in body_rows[:cap]:
            cells = r.css("td") or r.css("th")
            values = [_WS_RE.sub(" ", c.text(strip=True)) for c in cells]
            rec: dict[str, Any] = {}
            for f in schema.fields:
                idx = field_map[f.name]
                raw = values[idx] if idx is not None and idx < len(values) else None
                if raw is None or raw == "":
                    stats[f.name] = _bump(stats[f.name], misses=1)
                    continue
                try:
                    norm = self._normalizer.normalize(raw, f.type, base_url)
                except Exception:
                    stats[f.name] = _bump(stats[f.name], errors=1)
                    continue
                rec[f.name] = norm
                stats[f.name] = _bump(stats[f.name], hits=1)
            if rec:
                records.append(rec)
        return ExtractionResult(
            status="success" if records else "empty",
            strategy_used="table_extraction",
            records=records,
            field_diagnostics=stats,
        )

    def _exec_article(
        self,
        plan: ExtractionPlan,
        html: str,
        base_url: str,
        schema: IntentSchema,
    ) -> ExtractionResult:
        try:
            import trafilatura
        except ImportError:
            return ExtractionResult(
                status="empty",
                strategy_used="article_extraction",
                records=[],
                notes=["trafilatura not installed"],
            )
        extracted = trafilatura.extract(
            html,
            url=base_url,
            output_format="json",
            with_metadata=True,
            include_comments=False,
        )
        if not extracted:
            return ExtractionResult(
                status="empty",
                strategy_used="article_extraction",
                records=[],
                notes=["trafilatura returned nothing"],
            )
        import json as _json

        try:
            payload = _json.loads(extracted)
        except _json.JSONDecodeError:
            payload = {"text": extracted}
        record: dict[str, Any] = {}
        stats: dict[str, FieldStat] = {}
        mapping = {
            "title": "title",
            "author": "author",
            "date": "date",
            "publish_date": "date",
            "summary": "description",
            "description": "description",
            "text": "text",
            "content": "text",
            "body": "text",
            "url": "url",
        }
        for f in schema.fields:
            source_key = mapping.get(f.name, f.name)
            raw = payload.get(source_key) or payload.get(f.name)
            if raw is None or raw == "":
                stats[f.name] = FieldStat(hits=0, misses=1, errors=0)
                continue
            try:
                norm = self._normalizer.normalize(raw, f.type, base_url)
            except Exception:
                stats[f.name] = FieldStat(hits=0, misses=0, errors=1)
                continue
            record[f.name] = norm
            stats[f.name] = FieldStat(hits=1, misses=0, errors=0)
        return ExtractionResult(
            status="success" if record else "empty",
            strategy_used="article_extraction",
            records=[record] if record else [],
            field_diagnostics=stats,
        )

    def _exec_regex(
        self,
        plan: ExtractionPlan,
        tree: HTMLParser,
        base_url: str,
        schema: IntentSchema,
        cap: int,
    ) -> ExtractionResult:
        patterns_list = plan.regex_patterns or []
        if not patterns_list:
            return ExtractionResult(
                status="empty",
                strategy_used="visible_text_regex",
                records=[],
                notes=["no regex_patterns provided"],
            )
        patterns = {p.name: p.pattern for p in patterns_list[:10]}
        body = tree.body
        visible = body.text(separator=" ", strip=True) if body else ""
        stats: dict[str, FieldStat] = {f.name: FieldStat() for f in schema.fields}
        record: dict[str, Any] = {}
        for f in schema.fields:
            pattern = patterns.get(f.name)
            if not pattern:
                stats[f.name] = _bump(stats[f.name], misses=1)
                continue
            try:
                compiled = regex.compile(pattern, regex.IGNORECASE)
                m = compiled.search(visible, timeout=_REGEX_TIMEOUT_S)
            except (regex.error, TimeoutError):
                stats[f.name] = _bump(stats[f.name], errors=1)
                continue
            if not m:
                stats[f.name] = _bump(stats[f.name], misses=1)
                continue
            raw = m.group(1) if m.groups() else m.group(0)
            try:
                norm = self._normalizer.normalize(raw, f.type, base_url)
            except Exception:
                stats[f.name] = _bump(stats[f.name], errors=1)
                continue
            record[f.name] = norm
            stats[f.name] = _bump(stats[f.name], hits=1)
        return ExtractionResult(
            status="success" if record else "empty",
            strategy_used="visible_text_regex",
            records=[record] if record else [],
            field_diagnostics=stats,
        )

    def _exec_structured(
        self,
        plan: ExtractionPlan,
        html: str,
        base_url: str,
        schema: IntentSchema,
        cap: int,
    ) -> ExtractionResult:
        from spectus._core import structured_data

        sd = structured_data.extract(html)
        records: list[dict[str, Any]] = []
        stats: dict[str, FieldStat] = {f.name: FieldStat() for f in schema.fields}
        for payload in sd.raw_payloads[:5]:
            data = payload.payload
            if not isinstance(data, dict):
                continue
            items = data if "@graph" not in data else (data.get("@graph") or [data])
            if not isinstance(items, list):
                items = [items]
            for item in items:
                if not isinstance(item, dict):
                    continue
                rec, sub_stats = self._extract_from_dict(item, schema, base_url)
                if rec:
                    records.append(rec)
                for k, v in sub_stats.items():
                    cur = stats.get(k, FieldStat())
                    stats[k] = FieldStat(
                        hits=cur.hits + v.hits,
                        misses=cur.misses + v.misses,
                        errors=cur.errors + v.errors,
                    )
                if len(records) >= cap:
                    break
            if len(records) >= cap:
                break
        return ExtractionResult(
            status="success" if records else "empty",
            strategy_used="structured_data",
            records=records,
            field_diagnostics=stats,
        )

    def _extract_from_dict(
        self, item: dict, schema: IntentSchema, base_url: str
    ) -> tuple[dict[str, Any], dict[str, FieldStat]]:
        rec: dict[str, Any] = {}
        stats: dict[str, FieldStat] = {f.name: FieldStat() for f in schema.fields}
        for f in schema.fields:
            raw = _lookup_in_dict(item, f.name)
            if raw is None:
                stats[f.name] = _bump(stats[f.name], misses=1)
                continue
            if isinstance(raw, dict):
                raw = raw.get("name") or raw.get("@id") or raw.get("url") or str(raw)
            try:
                norm = self._normalizer.normalize(raw, f.type, base_url)
            except Exception:
                stats[f.name] = _bump(stats[f.name], errors=1)
                continue
            if norm is None or norm == "":
                stats[f.name] = _bump(stats[f.name], misses=1)
                continue
            rec[f.name] = norm
            stats[f.name] = _bump(stats[f.name], hits=1)
        return rec, stats

    def _extract_fields_from_root(
        self,
        root: Node,
        fields: dict[str, FieldSelector],
        base_url: str,
        schema: IntentSchema,
    ) -> tuple[dict[str, Any], dict[str, FieldStat]]:
        record: dict[str, Any] = {}
        stats: dict[str, FieldStat] = {f.name: FieldStat() for f in schema.fields}
        for f in schema.fields:
            fs = fields.get(f.name)
            if fs is None:
                stats[f.name] = _bump(stats[f.name], misses=1)
                continue
            raw = self._read_field(root, fs, base_url)
            if raw is None and fs.fallback_selector:
                fallback = FieldSelector(
                    name=fs.name,
                    selector=fs.fallback_selector,
                    attribute=fs.attribute,
                    type=fs.type,
                )
                raw = self._read_field(root, fallback, base_url)
            if raw is None:
                stats[f.name] = _bump(stats[f.name], misses=1)
                continue
            try:
                norm = self._normalizer.normalize(raw, f.type, base_url)
            except Exception:
                stats[f.name] = _bump(stats[f.name], errors=1)
                continue
            if norm is None or norm == "":
                stats[f.name] = _bump(stats[f.name], misses=1)
                continue
            record[f.name] = norm
            stats[f.name] = _bump(stats[f.name], hits=1)
        return record, stats

    def _read_field(self, root: Node, fs: FieldSelector, base_url: str) -> str | None:
        node = self._safe_css_first(root, fs.selector)
        if node is None:
            return None
        if fs.attribute == "text":
            return _WS_RE.sub(" ", node.text(strip=True)) or None
        raw = node.attributes.get(fs.attribute) if fs.attribute else None
        if raw is None:
            return None
        raw = raw.strip()
        if fs.attribute in ("href", "src") and raw:
            try:
                raw = urljoin(base_url, raw)
            except (ValueError, TypeError):
                pass
        return raw or None

    def _safe_css(self, root: Node, selector: str) -> list[Node]:
        if not selector or len(selector) > 500:
            raise InvalidSelectorError(detail="empty_or_too_long", selector=selector or "")
        nodes = _resolve_selector(root, selector)
        if not nodes:
            self._log.info("selector_no_match", selector=selector[:200])
        return nodes

    def _safe_css_first(self, root: Node, selector: str) -> Node | None:
        if not selector or len(selector) > 500:
            return None
        node = _resolve_selector_first(root, selector)
        if node is None:
            self._log.info("selector_no_match", selector=selector[:200])
        return node


def _bump(stat: FieldStat, hits: int = 0, misses: int = 0, errors: int = 0) -> FieldStat:
    return FieldStat(
        hits=stat.hits + hits,
        misses=stat.misses + misses,
        errors=stat.errors + errors,
    )


def _match_header_to_field(field_name: str, headers: list[str]) -> int | None:
    target = field_name.lower().replace("_", " ")
    for idx, h in enumerate(headers):
        if h == target or h == field_name.lower():
            return idx
    for idx, h in enumerate(headers):
        if target in h or h in target:
            return idx
    return None


def _lookup_in_dict(item: dict, field_name: str) -> Any:
    keys_to_try = [
        field_name,
        field_name.replace("_", ""),
        field_name.replace("_", "-"),
        _to_camel(field_name),
        _to_pascal(field_name),
    ]
    for key in keys_to_try:
        if key in item:
            return item[key]
    return None


def _to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def _to_pascal(name: str) -> str:
    return "".join(p.title() for p in name.split("_"))
