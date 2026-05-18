from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from app.config import Settings
    from app.db.repositories import ArtifactRepo, JobRepo, TemplateRepo
    from app.llm.client import LlmClient
    from app.services.artifacts import ArtifactsWriter
    from app.services.browser_pool import BrowserPool
    from app.services.browser_renderer import BrowserRenderer
    from app.services.compliance import ComplianceChecker
    from app.services.extraction_executor import ExtractionExecutor
    from app.services.extraction_planner import ExtractionPlanner
    from app.services.intent_parser import IntentParser
    from app.services.metrics import Metrics
    from app.services.page_analyzer import PageAnalyzer
    from app.services.repair_manager import RepairManager
    from app.services.semantic_extractor import SemanticExtractor
    from app.services.static_fetcher import StaticFetcher
    from app.services.template_manager import TemplateManager
    from app.services.validator import Validator


@dataclass(frozen=True)
class Pipeline:
    settings: "Settings"
    jobs: "JobRepo"
    artifact_repo: "ArtifactRepo"
    templates: "TemplateManager"
    artifacts: "ArtifactsWriter"
    compliance: "ComplianceChecker"
    static_fetcher: "StaticFetcher"
    browser_pool: "BrowserPool"
    browser_renderer: "BrowserRenderer"
    page_analyzer: "PageAnalyzer"
    intent_parser: "IntentParser"
    planner: "ExtractionPlanner"
    executor: "ExtractionExecutor"
    validator: "Validator"
    repair_mgr: "RepairManager"
    semantic: "SemanticExtractor"
    llm: "LlmClient"
    metrics: "Metrics"


def get_pipeline(request: Request) -> Pipeline:
    pipeline: Pipeline = request.app.state.pipeline
    return pipeline
