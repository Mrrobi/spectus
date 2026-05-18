from __future__ import annotations

import asyncio
import contextlib
from time import monotonic

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PWTimeout

from spectus._core.artifacts import ArtifactsWriter
from spectus._core.browser_pool import BrowserPool
from spectus._core.url_normalizer import NormalizedUrl
from spectus._schemas.execution import RenderResult
from spectus.config import Settings
from spectus.errors import BrowserRenderError
from spectus.logging import get_logger


class BrowserRenderer:
    def __init__(
        self,
        pool: BrowserPool,
        artifacts: ArtifactsWriter,
        settings: Settings,
    ) -> None:
        self._pool = pool
        self._artifacts = artifacts
        self._settings = settings
        self._log = get_logger("browser_renderer")

    async def render(
        self,
        url: NormalizedUrl,
        job_id: str,
        deadline_s: float,
        screenshot: bool = True,
    ) -> RenderResult:
        if not self._pool.is_available:
            raise BrowserRenderError(detail="pool_unavailable", reason="pool_unavailable")
        start = monotonic()

        async def _run() -> RenderResult:
            async with self._pool.acquire() as ctx:
                page = await ctx.new_page()
                try:
                    try:
                        await page.goto(
                            url.canonical,
                            timeout=int(deadline_s * 1000),
                            wait_until="domcontentloaded",
                        )
                    except PWTimeout as e:
                        raise BrowserRenderError(
                            detail="goto_timeout", reason="goto_timeout"
                        ) from e
                    except PlaywrightError as e:
                        raise BrowserRenderError(detail=str(e)[:300], reason="goto_error") from e
                    with contextlib.suppress(PWTimeout, PlaywrightError):
                        await page.wait_for_load_state(
                            "networkidle", timeout=min(3000, int(deadline_s * 1000))
                        )
                    try:
                        await asyncio.sleep(0.5)
                    except asyncio.CancelledError:
                        raise
                    html = await page.content()
                    final_url = page.url
                    screenshot_path: str | None = None
                    if screenshot:
                        try:
                            screenshot_path = await self._artifacts.write_screenshot(
                                job_id, await page.screenshot(full_page=False, type="png")
                            )
                        except Exception as e:
                            self._log.warning("screenshot_failed", error=str(e))
                    visible_text = await page.evaluate(
                        "() => document.body && document.body.innerText ? document.body.innerText.length : 0"
                    )
                    elapsed_ms = int((monotonic() - start) * 1000)
                    return RenderResult(
                        final_url=final_url,
                        html=html,
                        screenshot_path=screenshot_path,
                        elapsed_ms=elapsed_ms,
                        visible_text_length=int(visible_text or 0),
                    )
                finally:
                    with contextlib.suppress(Exception):
                        await page.close()

        try:
            return await asyncio.wait_for(_run(), timeout=deadline_s + 1.0)
        except TimeoutError as e:
            raise BrowserRenderError(detail="overall_timeout", reason="overall_timeout") from e
