from __future__ import annotations

import json
import re
from typing import Any

from spectus._schemas.page import StructuredDataSummary, StructuredPayload

_NEXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_NUXT_DATA_RE = re.compile(
    r"window\.__NUXT__\s*=\s*(\{.*?\});",
    re.IGNORECASE | re.DOTALL,
)
_INITIAL_STATE_RE = re.compile(
    r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});",
    re.IGNORECASE | re.DOTALL,
)
_JSON_LD_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_OG_RE = re.compile(
    r'<meta[^>]*property="(og:[^"]+)"[^>]*content="([^"]*)"',
    re.IGNORECASE,
)
_TWITTER_RE = re.compile(
    r'<meta[^>]*name="(twitter:[^"]+)"[^>]*content="([^"]*)"',
    re.IGNORECASE,
)
_MICRODATA_RE = re.compile(
    r'itemtype="https?://schema\.org/([A-Za-z]+)"',
    re.IGNORECASE,
)


_MAX_PAYLOAD_BYTES = 2048


def _truncate_payload(p: Any) -> dict[str, Any]:
    try:
        serialized = json.dumps(p, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {"truncated": True, "preview": str(p)[:_MAX_PAYLOAD_BYTES]}
    if len(serialized) <= _MAX_PAYLOAD_BYTES:
        return p if isinstance(p, dict) else {"value": p}
    return {"truncated": True, "preview": serialized[:_MAX_PAYLOAD_BYTES]}


def extract(html: str) -> StructuredDataSummary:
    json_ld_types: list[str] = []
    payloads: list[StructuredPayload] = []

    for match in _JSON_LD_RE.finditer(html):
        if len(payloads) >= 5:
            break
        raw = match.group(1).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("@type")
            if isinstance(t, str):
                json_ld_types.append(t)
            elif isinstance(t, list):
                json_ld_types.extend(str(x) for x in t if isinstance(x, (str, int)))
            payloads.append(StructuredPayload(source="json-ld", payload=_truncate_payload(item)))
            if len(payloads) >= 5:
                break

    open_graph: dict[str, str] = {}
    for m in _OG_RE.finditer(html):
        if len(open_graph) >= 30:
            break
        open_graph[m.group(1).lower()] = m.group(2)

    twitter: dict[str, str] = {}
    for m in _TWITTER_RE.finditer(html):
        if len(twitter) >= 30:
            break
        twitter[m.group(1).lower()] = m.group(2)

    microdata_types = sorted({m.group(1) for m in _MICRODATA_RE.finditer(html)})

    next_present = bool(_NEXT_DATA_RE.search(html))
    if next_present and len(payloads) < 5:
        m = _NEXT_DATA_RE.search(html)
        if m:
            raw = m.group(1).strip()
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    payloads.append(
                        StructuredPayload(source="next-data", payload=_truncate_payload(parsed))
                    )
            except json.JSONDecodeError:
                pass

    nuxt_present = bool(_NUXT_DATA_RE.search(html))
    initial_state_present = bool(_INITIAL_STATE_RE.search(html))

    return StructuredDataSummary(
        json_ld_types=sorted(set(json_ld_types)),
        open_graph=open_graph,
        twitter=twitter,
        microdata_types=microdata_types,
        next_data_present=next_present,
        nuxt_data_present=nuxt_present,
        initial_state_present=initial_state_present,
        raw_payloads=payloads,
    )
