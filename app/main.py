from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes_extractions import router as extractions_router
from app.api.routes_health import router as health_router
from app.api.routes_templates import router as templates_router
from app.config import Settings, get_settings
from app.db.repositories import ArtifactRepo, JobRepo, TemplateRepo
from app.db.session import dispose_engine, make_engine, make_sessionmaker
from app.deps import Pipeline
from app.errors import ExtractionError, SOFT_ERROR_CODES
from app.llm.client import LlmClient
from app.logging import configure_logging, get_logger
from app.services.artifacts import ArtifactsWriter
from app.services.browser_pool import BrowserPool
from app.services.browser_renderer import BrowserRenderer
from app.services.compliance import ComplianceChecker
from app.services.extraction_executor import ExtractionExecutor
from app.services.extraction_planner import ExtractionPlanner
from app.services.intent_parser import IntentParser
from app.services.metrics import Metrics
from app.services.normalizer import FieldNormalizer
from app.services.page_analyzer import PageAnalyzer
from app.services.repair_manager import RepairManager
from app.services.semantic_extractor import SemanticExtractor
from app.services.static_fetcher import StaticFetcher
from app.services.template_manager import TemplateManager
from app.services.validator import Validator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("lifespan")
    log.info("startup_begin", db_url=settings.db_url, pool_size=settings.browser_pool_size)

    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)

    engine = make_engine(settings.db_url)
    sessionmaker = make_sessionmaker(engine)

    http = httpx.AsyncClient(
        http2=True,
        timeout=httpx.Timeout(settings.http_timeout_sec, connect=settings.http_connect_timeout_sec),
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
    )

    browser_pool = BrowserPool(settings)
    await browser_pool.start()

    metrics = Metrics()
    llm = LlmClient(settings, metrics)
    artifacts = ArtifactsWriter(settings.artifacts_dir)

    jobs = JobRepo(sessionmaker)
    artifact_repo = ArtifactRepo(sessionmaker)
    template_repo = TemplateRepo(sessionmaker)

    compliance = ComplianceChecker(http, settings)
    static_fetcher = StaticFetcher(http, settings)
    browser_renderer = BrowserRenderer(browser_pool, artifacts, settings)
    page_analyzer = PageAnalyzer(settings)
    intent_parser = IntentParser(llm, settings)
    planner = ExtractionPlanner(llm, settings)
    normalizer = FieldNormalizer()
    executor = ExtractionExecutor(normalizer, settings)
    validator = Validator()
    template_manager = TemplateManager(template_repo)
    repair_mgr = RepairManager(llm, executor, validator, settings)
    semantic = SemanticExtractor(llm, settings)

    pipeline = Pipeline(
        settings=settings,
        jobs=jobs,
        artifact_repo=artifact_repo,
        templates=template_manager,
        artifacts=artifacts,
        compliance=compliance,
        static_fetcher=static_fetcher,
        browser_pool=browser_pool,
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
    app.state.pipeline = pipeline
    log.info("startup_done")

    try:
        yield
    finally:
        log.info("shutdown_begin")
        await browser_pool.stop()
        await http.aclose()
        await dispose_engine(engine)
        try:
            metrics.dump(settings.metrics_path)
        except Exception as e:
            log.warning("metrics_dump_failed", error=str(e))
        log.info("shutdown_done")


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="spectus",
        version="0.1.0",
        description="AI-assisted web data extractor",
        lifespan=lifespan,
    )

    @app.exception_handler(ExtractionError)
    async def _handle_extraction_error(request: Request, exc: ExtractionError) -> JSONResponse:
        log = get_logger("error_handler")
        log.log(
            exc.log_level,
            "extraction_error",
            code=exc.code,
            detail=exc.detail,
            path=request.url.path,
        )
        if exc.code in SOFT_ERROR_CODES:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "failed" if exc.code != "partial_success" else "partial_success",
                    "error": {"code": exc.code, "message": exc.user_message()},
                },
            )
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": {"code": exc.code, "message": exc.user_message()}},
        )

    app.include_router(health_router)
    app.include_router(extractions_router, prefix="/api")
    app.include_router(templates_router, prefix="/api")
    return app


app = create_app()
