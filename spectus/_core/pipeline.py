from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from spectus._core.artifacts import ArtifactsWriter
    from spectus._core.browser_pool import BrowserPool
    from spectus._core.browser_renderer import BrowserRenderer
    from spectus._core.compliance import ComplianceChecker
    from spectus._core.extraction_executor import ExtractionExecutor
    from spectus._core.extraction_planner import ExtractionPlanner
    from spectus._core.intent_parser import IntentParser
    from spectus._core.metrics import Metrics
    from spectus._core.page_analyzer import PageAnalyzer
    from spectus._core.repair_manager import RepairManager
    from spectus._core.semantic_extractor import SemanticExtractor
    from spectus._core.static_fetcher import StaticFetcher
    from spectus._core.template_manager import TemplateManager
    from spectus._core.validator import Validator
    from spectus._db.repositories import ArtifactRepo, JobRepo
    from spectus._llm.client import LlmClient
    from spectus.config import Settings


@dataclass(frozen=True)
class Pipeline:
    settings: Settings
    jobs: JobRepo
    artifact_repo: ArtifactRepo
    templates: TemplateManager
    artifacts: ArtifactsWriter
    compliance: ComplianceChecker
    static_fetcher: StaticFetcher
    browser_pool: BrowserPool
    browser_renderer: BrowserRenderer
    page_analyzer: PageAnalyzer
    intent_parser: IntentParser
    planner: ExtractionPlanner
    executor: ExtractionExecutor
    validator: Validator
    repair_mgr: RepairManager
    semantic: SemanticExtractor
    llm: LlmClient
    metrics: Metrics
