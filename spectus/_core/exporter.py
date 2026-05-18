from __future__ import annotations

import csv
import io
from typing import Any


def records_to_csv(records: list[dict[str, Any]], fieldnames: list[str] | None = None) -> str:
    if not records:
        return ""
    if fieldnames is None:
        seen: list[str] = []
        seen_set: set[str] = set()
        for r in records:
            for k in r.keys():
                if k not in seen_set:
                    seen.append(k)
                    seen_set.add(k)
        fieldnames = seen
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in records:
        flat = {k: _stringify(v) for k, v in r.items() if k in fieldnames}
        writer.writerow(flat)
    return buffer.getvalue()


def _stringify(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v)
    if isinstance(v, dict):
        return "; ".join(f"{k}={v[k]}" for k in sorted(v))
    return str(v)
