"""Field-level result merger. Picks the most plausible value per field
across multiple extraction passes, with source-aware tie-breakers.

Heuristics:
- Reject values failing type/length sanity for declared type.
- For URL / numeric / currency / date / email / phone types, when both standard
  (DOM) and semantic (LLM-from-text) produce plausible candidates, **prefer
  semantic**, since DOM selectors frequently pick fragments while semantic LLM
  reads labels in context.
- For string/list_string, prefer shorter to avoid page-dump artifacts.
- Tie-break: shorter value wins (avoids dumps).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from spectus._schemas.intent import FieldType, IntentSchema

_MAX_LEN_FOR_TYPE: dict[FieldType, int] = {
    "string": 4000,
    "number": 30,
    "integer": 20,
    "currency": 60,
    "url": 500,
    "email": 254,
    "phone": 30,
    "date": 60,
    "boolean": 10,
    "list_string": 4000,
}

_SEMANTIC_PREFERRED_TYPES = frozenset(
    {"url", "integer", "number", "currency", "date", "email", "phone"}
)


@dataclass(frozen=True)
class TaggedRecords:
    source: str
    records: list[dict[str, Any]]


def _length_of(v: Any) -> int:
    if v is None:
        return 0
    if isinstance(v, (list, tuple)):
        return sum(len(str(x)) for x in v)
    return len(str(v))


def _is_plausible(v: Any, ftype: FieldType) -> bool:
    if v is None or v in ("", []):
        return False
    n = _length_of(v)
    if n > _MAX_LEN_FOR_TYPE.get(ftype, 4000):
        return False
    if ftype == "url":
        if not isinstance(v, str):
            return False
        try:
            p = urlparse(v)
        except ValueError:
            return False
        return p.scheme in ("http", "https") and bool(p.netloc)
    if ftype in ("integer", "number") and isinstance(v, bool):
        return False
    if ftype == "boolean":
        return isinstance(v, bool) or (
            isinstance(v, str) and v.lower() in {"true", "false", "yes", "no", "0", "1"}
        )
    return True


def _pick_field(candidates: list[tuple[str, Any]], ftype: FieldType) -> Any:
    plausible = [(src, v) for src, v in candidates if _is_plausible(v, ftype)]
    if not plausible:
        for _, v in candidates:
            if v not in (None, "", []):
                return v
        return None
    if ftype in _SEMANTIC_PREFERRED_TYPES:
        for src, v in plausible:
            if src == "semantic":
                return v
        plausible.sort(key=lambda kv: _length_of(kv[1]))
        return plausible[0][1]
    plausible.sort(key=lambda kv: _length_of(kv[1]))
    return plausible[0][1]


def merge_tagged(
    sources: list[TaggedRecords],
    schema: IntentSchema,
) -> list[dict[str, Any]]:
    non_empty = [s for s in sources if s.records]
    if not non_empty:
        return []
    if schema.expected_output == "object":
        merged: dict[str, Any] = {}
        for f in schema.fields:
            candidates = [(s.source, s.records[0].get(f.name)) for s in non_empty]
            merged[f.name] = _pick_field(candidates, f.type)
        if all(v in (None, "", []) for v in merged.values()):
            return []
        return [merged]
    max_len = max(len(s.records) for s in non_empty)
    out: list[dict[str, Any]] = []
    for i in range(max_len):
        row_candidates: dict[str, list[tuple[str, Any]]] = {f.name: [] for f in schema.fields}
        for s in non_empty:
            if i >= len(s.records):
                continue
            for f in schema.fields:
                row_candidates[f.name].append((s.source, s.records[i].get(f.name)))
        merged_row = {f.name: _pick_field(row_candidates[f.name], f.type) for f in schema.fields}
        if any(v not in (None, "", []) for v in merged_row.values()):
            out.append(merged_row)
    return out


def merge_records(
    records_lists: list[list[dict[str, Any]]],
    schema: IntentSchema,
) -> list[dict[str, Any]]:
    """Convenience wrapper: assumes ['standard', 'semantic'] order."""
    sources = []
    labels = ("standard", "semantic", "other")
    for i, recs in enumerate(records_lists):
        sources.append(
            TaggedRecords(source=labels[i] if i < len(labels) else f"src_{i}", records=recs)
        )
    return merge_tagged(sources, schema)
