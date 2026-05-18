from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from time import monotonic
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from spectus.config import Settings
from spectus.errors import BrowserRenderError
from spectus.logging import get_logger


@dataclass
class _PooledContext:
    ctx: BrowserContext
    use_count: int = 0
    created_at: float = field(default_factory=monotonic)


class BrowserPool:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._queue: asyncio.Queue[_PooledContext] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._started = False
        self._log = get_logger("browser_pool")

    async def start(self) -> None:
        if self._started:
            return
        try:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=self._settings.browser_headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )
            for _ in range(self._settings.browser_pool_size):
                pc = await self._new_pooled()
                await self._queue.put(pc)
            self._started = True
            self._log.info("browser_pool_started", size=self._settings.browser_pool_size)
        except Exception as e:
            self._log.warning("browser_pool_start_failed", error=str(e))
            await self.stop()

    async def stop(self) -> None:
        while not self._queue.empty():
            try:
                pc = self._queue.get_nowait()
                try:
                    await pc.ctx.close()
                except Exception:
                    pass
            except asyncio.QueueEmpty:
                break
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None
        self._started = False
        self._log.info("browser_pool_stopped")

    @property
    def is_available(self) -> bool:
        return self._started and self._browser is not None

    async def _new_pooled(self) -> _PooledContext:
        if self._browser is None:
            raise BrowserRenderError(detail="browser_not_started", reason="not_started")
        ctx = await self._browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent=self._settings.user_agent,
            java_script_enabled=True,
            bypass_csp=False,
            service_workers="block",
        )
        return _PooledContext(ctx=ctx)

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[BrowserContext]:
        if not self._started or self._browser is None:
            raise BrowserRenderError(detail="pool_unavailable", reason="pool_unavailable")
        pc = await self._queue.get()
        try:
            try:
                await pc.ctx.clear_cookies()
            except Exception:
                pass
            yield pc.ctx
        finally:
            pc.use_count += 1
            age = monotonic() - pc.created_at
            if (
                pc.use_count >= self._settings.browser_recycle_uses
                or age > self._settings.browser_recycle_seconds
            ):
                try:
                    await pc.ctx.close()
                except Exception:
                    pass
                try:
                    pc = await self._new_pooled()
                except Exception as e:
                    self._log.warning("browser_recycle_failed", error=str(e))
            await self._queue.put(pc)
