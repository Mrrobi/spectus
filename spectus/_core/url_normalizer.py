from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import tldextract
from pydantic import BaseModel, ConfigDict

from spectus.errors import InvalidUrlError


class NormalizedUrl(BaseModel):
    model_config = ConfigDict(frozen=True)

    original: str
    canonical: str
    domain: str
    host: str
    scheme: str


_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
        "yclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "ref_src",
        "_hsenc",
        "_hsmi",
    }
)


def _clean_query(query: str) -> str:
    if not query:
        return ""
    pairs = [
        (k, v)
        for k, v in parse_qsl(query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    pairs.sort()
    return urlencode(pairs, doseq=True)


def normalize(raw: str) -> NormalizedUrl:
    if not raw or not raw.strip():
        raise InvalidUrlError("empty_url", url=raw or "")
    try:
        parsed = urlparse(raw.strip())
    except (ValueError, AttributeError) as e:
        raise InvalidUrlError("parse_failed", url=raw) from e

    if parsed.scheme.lower() not in ("http", "https"):
        raise InvalidUrlError(f"unsupported_scheme:{parsed.scheme}", url=raw)
    if not parsed.hostname:
        raise InvalidUrlError("missing_host", url=raw)

    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    port = parsed.port
    netloc = host
    if port is not None:
        default_port = 80 if scheme == "http" else 443
        if port != default_port:
            netloc = f"{host}:{port}"

    path = parsed.path or "/"
    query = _clean_query(parsed.query)
    canonical = urlunparse((scheme, netloc, path, "", query, ""))

    ext = tldextract.extract(host)
    if ext.domain and ext.suffix:
        registered = f"{ext.domain}.{ext.suffix}"
    elif ext.domain:
        registered = ext.domain
    else:
        registered = host

    return NormalizedUrl(
        original=raw,
        canonical=canonical,
        domain=registered,
        host=host,
        scheme=scheme,
    )
