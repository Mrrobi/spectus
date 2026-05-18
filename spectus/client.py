"""spectus public client. Thin wrapper around the in-process pipeline."""
from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path
from typing import Any

from spectus._schemas.api import ExtractionResponse
from spectus._core.extractor import Extractor


def _ensure_db() -> None:
    """Run alembic migrations if the DB doesn't exist yet."""
    db_url = os.environ.get("DB_URL", "sqlite+aiosqlite:///./spectus.db")
    if not db_url.startswith("sqlite"):
        return
    path = db_url.split("///", 1)[-1].lstrip("/").lstrip("\\")
    if not path or path == ":memory:":
        return
    db_file = Path(path)
    if db_file.exists() and db_file.stat().st_size > 0:
        return
    try:
        from alembic import command
        from alembic.config import Config

        cfg_path = Path(__file__).resolve().parent.parent / "alembic.ini"
        if not cfg_path.exists():
            return
        cfg = Config(str(cfg_path))
        command.upgrade(cfg, "head")
    except Exception:
        # User can run `spectus migrate` manually if this fails.
        pass


def _response_to_dict(resp: ExtractionResponse) -> dict[str, Any]:
    """Strip Pydantic envelope to plain dict for external consumers."""
    payload = resp.model_dump(mode="json")
    records = payload.get("records")
    if records is None:
        records = []
    elif isinstance(records, dict):
        records = [records]
    return {
        "status": payload["status"],
        "url": payload["url"],
        "instruction": payload["instruction"],
        "records": records,
        "diagnostics": payload["diagnostics"],
        "message": payload.get("message"),
    }


_SETTABLE_KEYS = frozenset({
    "openai_api_key",
    "openai_model_intent",
    "openai_model_plan",
    "openai_model_repair",
    "db_url",
    "artifacts_dir",
    "metrics_path",
    "user_agent",
    "browser_pool_size",
    "browser_headless",
    "rate_limit_rps",
    "rate_limit_burst",
    "allow_private_targets",
    "job_deadline_sec",
    "llm_intent_timeout_sec",
    "llm_planner_timeout_sec",
    "llm_repair_timeout_sec",
    "max_records_hard_cap",
    "max_html_bytes",
    "log_level",
})


def _collect_overrides(
    openai_api_key: str | None,
    extra: dict | None,
) -> dict:
    overrides: dict = {}
    if openai_api_key is not None:
        overrides["openai_api_key"] = openai_api_key
    if extra:
        for k, v in extra.items():
            if k not in _SETTABLE_KEYS:
                raise ValueError(f"unknown settings key: {k!r}")
            overrides[k] = v
    return overrides


class Client:
    """Async spectus client. Reuses browser pool + DB across calls."""

    def __init__(self, extractor: Extractor) -> None:
        self._extractor = extractor

    @classmethod
    async def create(
        cls,
        *,
        openai_api_key: str | None = None,
        browser: bool = True,
        log_level: str = "WARNING",
        settings: dict | None = None,
    ) -> "Client":
        """Create a new client.

        :param openai_api_key: override OPENAI_API_KEY for this client. If
            None, falls back to the env var.
        :param browser: launch Playwright pool. False = static-only.
        :param log_level: structlog level.
        :param settings: dict of any other Settings overrides
            (db_url, openai_model_*, browser_pool_size, ...). Unknown keys
            raise ValueError.
        """
        _ensure_db()
        overrides = _collect_overrides(openai_api_key, settings)
        extractor = await Extractor.create(
            browser=browser,
            log_level=log_level,
            settings_overrides=overrides,
        )
        return cls(extractor)

    async def extract(
        self,
        url: str,
        instruction: str,
        *,
        use_browser: str = "auto",
        max_records: int = 100,
        save_template: bool = True,
    ) -> dict[str, Any]:
        resp = await self._extractor.extract(
            url=url,
            instruction=instruction,
            use_browser=use_browser,
            max_records=max_records,
            save_template=save_template,
        )
        return _response_to_dict(resp)

    async def close(self) -> None:
        await self._extractor.close()

    async def __aenter__(self) -> "Client":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()


class SyncClient:
    """Synchronous wrapper. Runs an asyncio loop in a background thread so
    sync code (Django views, Flask, scripts, notebooks) can call .extract()
    without touching asyncio.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client: Client | None = None
        self._ready = threading.Event()

    @classmethod
    def open(
        cls,
        *,
        openai_api_key: str | None = None,
        browser: bool = True,
        log_level: str = "WARNING",
        settings: dict | None = None,
    ) -> "SyncClient":
        sc = cls()
        sc._start(
            openai_api_key=openai_api_key,
            browser=browser,
            log_level=log_level,
            settings=settings,
        )
        return sc

    def _start(
        self,
        *,
        openai_api_key: str | None,
        browser: bool,
        log_level: str,
        settings: dict | None,
    ) -> None:
        def runner() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)

            async def init() -> None:
                self._client = await Client.create(
                    openai_api_key=openai_api_key,
                    browser=browser,
                    log_level=log_level,
                    settings=settings,
                )

            loop.run_until_complete(init())
            self._ready.set()
            loop.run_forever()

        self._thread = threading.Thread(target=runner, daemon=True, name="spectus-loop")
        self._thread.start()
        self._ready.wait(timeout=120)
        if self._client is None:
            raise RuntimeError("SyncClient failed to initialize within 120s")

    def extract(
        self,
        url: str,
        instruction: str,
        *,
        use_browser: str = "auto",
        max_records: int = 100,
        save_template: bool = True,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        if self._loop is None or self._client is None:
            raise RuntimeError("SyncClient not initialized — use SyncClient.open()")
        future = asyncio.run_coroutine_threadsafe(
            self._client.extract(
                url=url,
                instruction=instruction,
                use_browser=use_browser,
                max_records=max_records,
                save_template=save_template,
            ),
            self._loop,
        )
        return future.result(timeout=timeout)

    def close(self) -> None:
        if self._loop is None or self._client is None:
            return
        future = asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
        try:
            future.result(timeout=30)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._loop = None
        self._client = None
        self._thread = None

    def __enter__(self) -> "SyncClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def extract(
    url: str,
    instruction: str,
    *,
    openai_api_key: str | None = None,
    use_browser: str = "auto",
    max_records: int = 100,
    save_template: bool = True,
    browser: bool = True,
    settings: dict | None = None,
) -> dict[str, Any]:
    """One-shot synchronous extract. Spins up the pipeline, runs, tears down.

    :param openai_api_key: pass the OpenAI key directly (skips OPENAI_API_KEY
        env var lookup).
    :param settings: dict of any other Settings overrides — e.g.
        {"openai_model_plan": "gpt-4o-mini", "browser_pool_size": 1}.

    For multiple calls, use `SyncClient` or `Client` to amortize browser-pool
    startup cost.
    """

    async def _run() -> dict[str, Any]:
        client = await Client.create(
            openai_api_key=openai_api_key,
            browser=browser,
            log_level="WARNING",
            settings=settings,
        )
        try:
            return await client.extract(
                url=url,
                instruction=instruction,
                use_browser=use_browser,
                max_records=max_records,
                save_template=save_template,
            )
        finally:
            await client.close()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        # Running event loop (Jupyter, IPython, FastAPI route, etc).
        # Run the coroutine in a dedicated background thread with its own loop.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(_run())).result()
    return asyncio.run(_run())
