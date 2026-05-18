from __future__ import annotations

from time import monotonic

import httpx

from spectus._core.url_normalizer import NormalizedUrl
from spectus._schemas.execution import FetchResult
from spectus.config import Settings
from spectus.errors import FetchError, UnsupportedContentTypeError
from spectus.logging import get_logger

_ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "application/xml", "text/xml")


class StaticFetcher:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings
        self._log = get_logger("static_fetcher")

    async def fetch(self, url: NormalizedUrl, deadline_s: float) -> FetchResult:
        start = monotonic()
        try:
            r = await self._http.get(
                url.canonical,
                timeout=httpx.Timeout(deadline_s, connect=self._settings.http_connect_timeout_sec),
                headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
            )
        except httpx.TimeoutException as e:
            raise FetchError(detail=f"timeout:{url.canonical}", reason="timeout") from e
        except httpx.HTTPError as e:
            raise FetchError(detail=str(e), reason=type(e).__name__) from e

        if r.status_code >= 400:
            raise FetchError(
                detail=f"http_{r.status_code}:{url.canonical}",
                reason=f"http_{r.status_code}",
            )

        content_type = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
        if content_type and not any(content_type.startswith(c) for c in _ALLOWED_CONTENT_TYPES):
            raise UnsupportedContentTypeError(detail=content_type, ct=content_type)

        body = r.content
        if len(body) > self._settings.max_html_bytes:
            self._log.warning(
                "html_too_large",
                url=url.canonical,
                bytes=len(body),
                cap=self._settings.max_html_bytes,
            )
            body = body[: self._settings.max_html_bytes]

        try:
            html = body.decode(r.encoding or "utf-8", errors="replace")
        except (LookupError, TypeError):
            html = body.decode("utf-8", errors="replace")

        elapsed_ms = int((monotonic() - start) * 1000)
        return FetchResult(
            final_url=str(r.url),
            status_code=r.status_code,
            headers=dict(r.headers),
            html=html,
            elapsed_ms=elapsed_ms,
            content_type=content_type or "text/html",
        )
