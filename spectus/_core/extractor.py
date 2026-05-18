"""Notebook helper for spectus. In-process client — no HTTP server required.

Usage:
    from spectus._core.extractor import Extractor
    ex = await Extractor.create()
    resp = await ex.extract("https://news.ycombinator.com/",
                             "Extract top stories: title, points, author, comments_count, story_url")
    ex.show(resp)
    ex.save_csv(resp, "hn.csv")
    await ex.close()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from spectus._core.artifacts import ArtifactsWriter
from spectus._core.browser_pool import BrowserPool
from spectus._core.browser_renderer import BrowserRenderer
from spectus._core.compliance import ComplianceChecker
from spectus._core.exporter import records_to_csv
from spectus._core.extraction_executor import ExtractionExecutor
from spectus._core.extraction_planner import ExtractionPlanner
from spectus._core.intent_parser import IntentParser
from spectus._core.metrics import Metrics
from spectus._core.normalizer import FieldNormalizer
from spectus._core.orchestrator import run_extraction
from spectus._core.page_analyzer import PageAnalyzer
from spectus._core.pipeline import Pipeline
from spectus._core.repair_manager import RepairManager
from spectus._core.semantic_extractor import SemanticExtractor
from spectus._core.static_fetcher import StaticFetcher
from spectus._core.template_manager import TemplateManager
from spectus._core.validator import Validator
from spectus._db.repositories import ArtifactRepo, JobRepo, TemplateRepo
from spectus._db.session import dispose_engine, make_engine, make_sessionmaker
from spectus._llm.client import LlmClient
from spectus._schemas.api import ExtractionOptions, ExtractionRequest, ExtractionResponse
from spectus._schemas.template import Template
from spectus.config import Settings, get_settings
from spectus.logging import configure_logging


class Extractor:
    """In-process spectus. Owns DB, HTTP client, browser pool, all services."""

    def __init__(self) -> None:
        self.settings: Settings | None = None
        self._engine = None
        self._http: httpx.AsyncClient | None = None
        self._browser_pool: BrowserPool | None = None
        self.pipeline: Pipeline | None = None

    @classmethod
    async def create(
        cls,
        *,
        log_level: str = "WARNING",
        browser: bool = True,
        settings_overrides: dict | None = None,
    ) -> Extractor:
        ex = cls()
        ex.settings = get_settings()
        overrides: dict = dict(settings_overrides or {})
        if not browser:
            overrides.setdefault("browser_pool_size", 0)
        if overrides:
            ex.settings = ex.settings.model_copy(update=overrides)
        configure_logging(log_level)
        ex.settings.artifacts_dir.mkdir(parents=True, exist_ok=True)

        ex._engine = make_engine(ex.settings.db_url)
        sm = make_sessionmaker(ex._engine)
        ex._http = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(
                ex.settings.http_timeout_sec, connect=ex.settings.http_connect_timeout_sec
            ),
            headers={"User-Agent": ex.settings.user_agent},
            follow_redirects=True,
        )
        ex._browser_pool = BrowserPool(ex.settings)
        if browser:
            await ex._browser_pool.start()

        metrics = Metrics()
        llm = LlmClient(ex.settings, metrics)
        artifacts = ArtifactsWriter(ex.settings.artifacts_dir)
        jobs = JobRepo(sm)
        artifact_repo = ArtifactRepo(sm)
        template_repo = TemplateRepo(sm)
        compliance = ComplianceChecker(ex._http, ex.settings)
        static_fetcher = StaticFetcher(ex._http, ex.settings)
        browser_renderer = BrowserRenderer(ex._browser_pool, artifacts, ex.settings)
        page_analyzer = PageAnalyzer(ex.settings)
        intent_parser = IntentParser(llm, ex.settings)
        planner = ExtractionPlanner(llm, ex.settings)
        normalizer = FieldNormalizer()
        executor = ExtractionExecutor(normalizer, ex.settings)
        validator = Validator()
        template_manager = TemplateManager(template_repo)
        repair_mgr = RepairManager(llm, executor, validator, ex.settings)
        semantic = SemanticExtractor(llm, ex.settings)

        ex.pipeline = Pipeline(
            settings=ex.settings,
            jobs=jobs,
            artifact_repo=artifact_repo,
            templates=template_manager,
            artifacts=artifacts,
            compliance=compliance,
            static_fetcher=static_fetcher,
            browser_pool=ex._browser_pool,
            browser_renderer=browser_renderer,
            page_analyzer=page_analyzer,
            intent_parser=intent_parser,
            planner=planner,
            executor=executor,
            validator=validator,
            repair_mgr=repair_mgr,
            semantic=semantic,
            llm=llm,
            metrics=metrics,
        )
        return ex

    async def extract(
        self,
        url: str,
        instruction: str,
        *,
        use_browser: str = "auto",
        max_records: int = 100,
        save_template: bool = True,
    ) -> ExtractionResponse:
        assert self.pipeline is not None
        req = ExtractionRequest(
            url=url,
            instruction=instruction,
            output_format="json",
            options=ExtractionOptions(
                use_browser=use_browser,
                max_records=max_records,
                save_template=save_template,
            ),
        )
        return await run_extraction(req, self.pipeline)

    async def list_templates(self, status: str | None = None) -> list[Template]:
        assert self.pipeline is not None
        return await self.pipeline.templates.list_all(status)

    async def metrics(self) -> dict[str, Any]:
        assert self.pipeline is not None
        return self.pipeline.metrics.snapshot()

    async def close(self) -> None:
        if self._browser_pool:
            await self._browser_pool.stop()
        if self._http:
            await self._http.aclose()
        if self._engine:
            await dispose_engine(self._engine)

    @staticmethod
    def records(resp: ExtractionResponse) -> list[dict[str, Any]]:
        recs = resp.records
        if recs is None:
            return []
        if isinstance(recs, dict):
            return [recs]
        return list(recs)

    @staticmethod
    def show(resp: ExtractionResponse, n: int = 5) -> None:
        d = resp.diagnostics
        print(f"status:   {resp.status}")
        print(f"strategy: {d.strategy_used}  mode: {d.static_or_browser}  page_type: {d.page_type}")
        print(
            f"records:  {d.records_found}  quality: {d.quality_score}  "
            f"repairs: {d.repair_attempts}  template: {d.template_used}"
        )
        print(
            f"runtime:  {d.runtime_ms} ms  llm_calls: {d.llm_calls}  "
            f"tokens_in: {d.llm_tokens_in}  tokens_out: {d.llm_tokens_out}"
        )
        if resp.message:
            print(f"message:  {resp.message}")
        if d.warnings:
            print(f"warnings: {d.warnings}")
        recs = Extractor.records(resp)
        print(f"\nfirst {min(n, len(recs))} of {len(recs)} records:")
        for i, r in enumerate(recs[:n]):
            print(f"  [{i}] {json.dumps(r, ensure_ascii=False)[:400]}")

    @staticmethod
    def to_dataframe(resp: ExtractionResponse):
        """Return pandas DataFrame. Requires `pip install pandas`."""
        import pandas as pd  # type: ignore[import-not-found]

        return pd.DataFrame(Extractor.records(resp))

    @staticmethod
    def save_csv(resp: ExtractionResponse, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(records_to_csv(Extractor.records(resp)), encoding="utf-8")
        return out

    @staticmethod
    def save_json(resp: ExtractionResponse, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "url": resp.url,
                    "instruction": resp.instruction,
                    "status": resp.status,
                    "diagnostics": resp.diagnostics.model_dump(mode="json"),
                    "records": Extractor.records(resp),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return out
