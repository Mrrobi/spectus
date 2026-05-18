from __future__ import annotations

import asyncio
import contextlib
import hashlib
from typing import Any
from uuid import UUID

from spectus._core.budget import BudgetTracker
from spectus._core.bundle_builder import build_facts_bundle
from spectus._core.merger import TaggedRecords, merge_tagged
from spectus._core.pipeline import Pipeline
from spectus._core.repair_manager import RepairContext
from spectus._core.url_normalizer import normalize
from spectus._schemas.api import ExtractionRequest, ExtractionResponse
from spectus._schemas.diagnostics import Diagnostics
from spectus._schemas.execution import ExtractionResult, FetchResult
from spectus._schemas.intent import IntentSchema
from spectus._schemas.page import CompactPage
from spectus._schemas.plan import ExtractionPlan
from spectus._schemas.validation import ValidationReport
from spectus.errors import (
    BudgetExceededError,
    ExtractionError,
    ExtractionPlanError,
    LlmTransientError,
    SchemaGenerationError,
)
from spectus.logging import get_logger, job_log_context


def idempotency_key(url: str, instruction: str) -> str:
    payload = f"{url}\n{instruction}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


async def run_extraction(req: ExtractionRequest, deps: Pipeline) -> ExtractionResponse:
    budget = BudgetTracker(total_s=deps.settings.job_deadline_sec)
    log = get_logger("orchestrator")
    instruction = req.instruction.strip()
    raw_url = str(req.url)
    idem_key = idempotency_key(raw_url, instruction)

    existing = await deps.jobs.find_by_idempotency_key(idem_key)
    if existing is not None and existing.status in ("success", "partial_success"):
        return await _hydrate_existing(existing, deps)

    url = normalize(raw_url)
    job_id = await deps.jobs.create(
        url=raw_url,
        domain=url.domain,
        instruction=instruction,
        idempotency_key=idem_key,
        output_format=req.output_format,
    )

    with job_log_context(str(job_id)):
        log.info("extraction_begin", url=url.canonical, instruction=instruction[:200])
        deps.metrics.inc("extraction_total", 1, status="started")
        try:
            response = await _run_pipeline(req, url, job_id, budget, deps)
            await deps.jobs.update_status(
                job_id,
                status=response.status,
                quality_score=response.diagnostics.quality_score,
                strategy_used=response.diagnostics.strategy_used,
                page_type=response.diagnostics.page_type,
                repair_attempts=response.diagnostics.repair_attempts,
                runtime_ms=response.diagnostics.runtime_ms,
            )
            await deps.jobs.save_result(
                job_id,
                response.records
                if isinstance(response.records, list)
                else [response.records]
                if response.records
                else [],
                response.diagnostics.model_dump(mode="json"),
            )
            deps.metrics.inc("extraction_total", 1, status=response.status)
            log.info(
                "job_summary",
                status=response.status,
                strategy=response.diagnostics.strategy_used,
                page_type=response.diagnostics.page_type,
                records=response.diagnostics.records_found,
                quality=response.diagnostics.quality_score,
                repair_attempts=response.diagnostics.repair_attempts,
                template_used=response.diagnostics.template_used,
                llm_calls=response.diagnostics.llm_calls,
                total_ms=response.diagnostics.runtime_ms,
            )
            return response
        except ExtractionError as e:
            deps.metrics.inc("errors_total", 1, code=e.code)
            await deps.jobs.update_status(
                job_id,
                status="failed",
                error_code=e.code,
                error_message=e.user_message()[:1990],
                runtime_ms=int(budget.elapsed() * 1000),
            )
            with contextlib.suppress(Exception):
                await deps.artifacts.write_error(
                    str(job_id),
                    {"code": e.code, "detail": e.detail, "message": e.user_message()},
                )
            log.warning("extraction_error", code=e.code, detail=e.detail)
            raise


async def _run_pipeline(
    req: ExtractionRequest,
    url,
    job_id: UUID,
    budget: BudgetTracker,
    deps: Pipeline,
) -> ExtractionResponse:
    job_id_str = str(job_id)
    log = get_logger("orchestrator")
    warnings: list[str] = []

    budget.assert_at_least(0.3, "compliance")
    await deps.compliance.check(url)

    fetch_budget = min(budget.remaining_for("fetch", 8.0), 8.0)
    intent_task: asyncio.Task[IntentSchema] = asyncio.create_task(
        deps.intent_parser.parse(
            req.instruction, url.canonical, job_id=job_id_str, artifact_writer=deps.artifacts
        )
    )
    fetch_task: asyncio.Task[FetchResult] = asyncio.create_task(
        deps.static_fetcher.fetch(url, fetch_budget)
    )
    try:
        intent, raw = await asyncio.gather(intent_task, fetch_task)
    except SchemaGenerationError:
        fetch_task.cancel()
        raise
    except Exception:
        intent_task.cancel()
        raise

    await deps.artifacts.write_html(job_id_str, "raw.html", raw.html)
    compact = deps.page_analyzer.analyze(raw.html, url.canonical)
    await deps.artifacts.write_json(
        job_id_str, "compact.json", compact.model_dump(mode="json", exclude_none=True)
    )
    await deps.artifacts.write_json(job_id_str, "intent.json", intent.model_dump(mode="json"))

    template = await deps.templates.find(url.domain, url.canonical, intent)
    template_used = False
    template_id: UUID | None = None
    repair_attempts = 0
    static_or_browser = "static"
    html_for_exec = raw.html

    if template is not None:
        log.info("template_hit", template_id=str(template.id), status=template.status)
        deps.metrics.inc("template_hit_total")
        try:
            if template.plan.strategy == "semantic_extraction":
                t_bundle = build_facts_bundle(html_for_exec, url.canonical)
                t_result = await deps.semantic.extract(
                    t_bundle,
                    intent,
                    req.instruction,
                    job_id=job_id_str,
                    artifact_writer=deps.artifacts,
                    max_records=req.options.max_records,
                )
            else:
                t_result = deps.executor.execute(
                    template.plan, html_for_exec, url.canonical, intent, req.options.max_records
                )
            t_report = deps.validator.validate(t_result, intent, compact)
            if t_report.good_enough:
                await deps.templates.record_success(template.id, t_report.overall_score)
                await _persist_artifacts(
                    deps, job_id_str, template.plan, t_report, t_result, intent
                )
                return _build_response(
                    job_id=job_id,
                    req=req,
                    intent=intent,
                    result=t_result,
                    report=t_report,
                    compact=compact,
                    static_or_browser=static_or_browser,
                    template_used=True,
                    template_id=template.id,
                    repair_attempts=0,
                    runtime_ms=int(budget.elapsed() * 1000),
                    warnings=warnings,
                    metrics_snapshot=_summarize_llm(deps),
                )
            else:
                await deps.templates.record_failure(template.id)
                warnings.append(f"template {template.id} failed validation; falling back")
        except ExtractionError as e:
            await deps.templates.record_failure(template.id)
            warnings.append(f"template {template.id} raised {e.code}; falling back")
    else:
        deps.metrics.inc("template_skip_total")

    needs_browser = req.options.use_browser == "force" or (
        req.options.use_browser == "auto"
        and not deps.page_analyzer.is_sufficient_for(compact, intent)
    )
    if req.options.use_browser == "never":
        needs_browser = False

    if needs_browser and deps.browser_pool.is_available:
        render_budget = budget.remaining_for("browser_render", 15.0)
        try:
            rendered = await deps.browser_renderer.render(
                url, job_id_str, render_budget, screenshot=True
            )
            await deps.artifacts.write_html(job_id_str, "rendered.html", rendered.html)
            compact = deps.page_analyzer.analyze(rendered.html, url.canonical)
            await deps.artifacts.write_json(
                job_id_str,
                "compact.rendered.json",
                compact.model_dump(mode="json", exclude_none=True),
            )
            html_for_exec = rendered.html
            static_or_browser = "browser"
            deps.metrics.inc("browser_render_total")
        except ExtractionError as e:
            warnings.append(f"browser_render_failed:{e.code}; using static html")

    budget.assert_at_least(1.5, "planner")
    try:
        plan: ExtractionPlan = await deps.planner.plan(
            req.instruction,
            intent,
            compact,
            job_id=job_id_str,
            artifact_writer=deps.artifacts,
        )
    except LlmTransientError:
        raise
    except ExtractionPlanError:
        raise

    result = deps.executor.execute(
        plan, html_for_exec, url.canonical, intent, req.options.max_records
    )
    report = deps.validator.validate(result, intent, compact)
    await deps.artifacts.write_json(job_id_str, "plan.json", plan.model_dump(mode="json"))
    await deps.artifacts.write_json(job_id_str, "validation.json", report.model_dump(mode="json"))

    while report.needs_repair and repair_attempts < 2 and budget.remaining() > 8.0:
        repair_attempts += 1
        deps.metrics.inc("repair_attempts_total")
        try:
            plan, result, report = await deps.repair_mgr.repair_once(
                RepairContext(
                    intent=intent,
                    prev_plan=plan,
                    prev_report=report,
                    compact=compact,
                    html=html_for_exec,
                    base_url=url.canonical,
                    instruction=req.instruction,
                    max_records=req.options.max_records,
                ),
                job_id=job_id_str,
                attempt=repair_attempts,
                artifact_writer=deps.artifacts,
            )
            await deps.artifacts.write_json(
                job_id_str,
                f"plan_repair_{repair_attempts}.json",
                plan.model_dump(mode="json"),
            )
            await deps.artifacts.write_json(
                job_id_str,
                f"validation_repair_{repair_attempts}.json",
                report.model_dump(mode="json"),
            )
        except BudgetExceededError:
            break
        except ExtractionError as e:
            warnings.append(f"repair_{repair_attempts}_failed:{e.code}")
            break

    run_semantic = (
        intent.expected_output == "object" or not report.good_enough or repair_attempts > 0
    )
    if run_semantic and budget.remaining() > 8.0:
        log.info("semantic_run_start", reason_quality=report.overall_score)
        deps.metrics.inc("semantic_run_total")
        try:
            bundle = build_facts_bundle(html_for_exec, url.canonical)
            sem_result = await deps.semantic.extract(
                bundle,
                intent,
                req.instruction,
                job_id=job_id_str,
                artifact_writer=deps.artifacts,
                max_records=req.options.max_records,
            )
            sem_report = deps.validator.validate(sem_result, intent, compact)
            await deps.artifacts.write_json(
                job_id_str,
                "semantic_result.json",
                {"records": sem_result.records, "strategy": sem_result.strategy_used},
            )
            await deps.artifacts.write_json(
                job_id_str,
                "semantic_validation.json",
                sem_report.model_dump(mode="json"),
            )

            merged_records = merge_tagged(
                [
                    TaggedRecords(source="standard", records=result.records),
                    TaggedRecords(source="semantic", records=sem_result.records),
                ],
                intent,
            )
            merged_result = ExtractionResult(
                status="success" if merged_records else "empty",
                strategy_used=(
                    sem_result.strategy_used
                    if sem_report.overall_score > report.overall_score
                    else result.strategy_used
                ),
                records=merged_records,
                field_diagnostics=result.field_diagnostics,
                notes=result.notes + sem_result.notes,
            )
            merged_report = deps.validator.validate(merged_result, intent, compact)
            await deps.artifacts.write_json(
                job_id_str,
                "merged_validation.json",
                merged_report.model_dump(mode="json"),
            )

            candidates = [
                ("merged", merged_result, merged_report),
                ("semantic", sem_result, sem_report),
                ("standard", result, report),
            ]
            best_name, best_result, best_report = max(candidates, key=lambda x: x[2].overall_score)
            log.info(
                "result_pick",
                pick=best_name,
                merged=merged_report.overall_score,
                semantic=sem_report.overall_score,
                standard=report.overall_score,
            )
            result = best_result
            report = best_report
        except ExtractionError as e:
            warnings.append(f"semantic_run_failed:{e.code}")
        except Exception as e:
            warnings.append(f"semantic_run_error:{type(e).__name__}")
            log.warning("semantic_run_unexpected", error=str(e))

    if report.good_enough and req.options.save_template:
        try:
            save_plan = plan
            if result.strategy_used == "semantic_extraction":
                save_plan = plan.model_copy(update={"strategy": "semantic_extraction"})
            template_id = await deps.templates.record_new_candidate(
                domain=url.domain,
                url=url.canonical,
                schema=intent,
                page_type=compact.page_type_hint,
                plan=save_plan,
                score=report.overall_score,
            )
        except Exception as e:
            log.warning("template_save_failed", error=str(e))
            warnings.append("template_save_failed")

    if not report.good_enough and not result.records and report.overall_score < 0.1:
        if result.status != "success":
            warnings.append("no records produced; review compact representation")

    runtime_ms = int(budget.elapsed() * 1000)
    deps.metrics.observe("extraction_latency_ms", runtime_ms, mode=static_or_browser)
    deps.metrics.observe("quality_score", report.overall_score, mode=static_or_browser)
    deps.metrics.inc("extraction_strategy_used", 1, strategy=plan.strategy)

    return _build_response(
        job_id=job_id,
        req=req,
        intent=intent,
        result=result,
        report=report,
        compact=compact,
        static_or_browser=static_or_browser,
        template_used=template_used,
        template_id=template_id,
        repair_attempts=repair_attempts,
        runtime_ms=runtime_ms,
        warnings=warnings,
        metrics_snapshot=_summarize_llm(deps),
    )


def _summarize_llm(deps: Pipeline) -> dict[str, int]:
    snap = deps.metrics.snapshot()
    calls = sum(v for k, v in snap["counters"].items() if k.startswith("llm_calls_total"))
    tin = sum(
        v
        for k, v in snap["counters"].items()
        if k.startswith("llm_tokens_total") and "direction=in" in k
    )
    tout = sum(
        v
        for k, v in snap["counters"].items()
        if k.startswith("llm_tokens_total") and "direction=out" in k
    )
    return {"llm_calls": calls, "llm_tokens_in": tin, "llm_tokens_out": tout}


def _build_response(
    *,
    job_id: UUID,
    req: ExtractionRequest,
    intent: IntentSchema,
    result: ExtractionResult,
    report: ValidationReport,
    compact: CompactPage,
    static_or_browser: str,
    template_used: bool,
    template_id: UUID | None,
    repair_attempts: int,
    runtime_ms: int,
    warnings: list[str],
    metrics_snapshot: dict[str, int],
) -> ExtractionResponse:
    field_coverage = {}
    for name, stat in result.field_diagnostics.items():
        total = stat.hits + stat.misses + stat.errors
        field_coverage[name] = stat.hits / total if total else 0.0
    status: str
    if report.good_enough:
        status = "success"
    elif result.records or report.overall_score >= 0.3:
        status = "partial_success"
    else:
        status = "failed"
    records_out: Any
    if intent.expected_output == "object":
        records_out = result.records[0] if result.records else None
    else:
        records_out = result.records
    return ExtractionResponse(
        job_id=job_id,
        status=status,  # type: ignore[arg-type]
        url=str(req.url),
        instruction=req.instruction,
        records=records_out,
        diagnostics=Diagnostics(
            strategy_used=result.strategy_used,
            page_type=compact.page_type_hint,
            static_or_browser=static_or_browser,  # type: ignore[arg-type]
            records_found=len(result.records),
            quality_score=round(report.overall_score, 4),
            field_coverage=field_coverage,
            missing_required=report.missing_required,
            repair_attempts=repair_attempts,
            template_used=template_used,
            template_id=template_id,
            runtime_ms=runtime_ms,
            llm_calls=metrics_snapshot.get("llm_calls", 0),
            llm_tokens_in=metrics_snapshot.get("llm_tokens_in", 0),
            llm_tokens_out=metrics_snapshot.get("llm_tokens_out", 0),
            warnings=warnings,
        ),
        message=report.repair_hint if not report.good_enough else None,
    )


async def _hydrate_existing(existing, deps: Pipeline) -> ExtractionResponse:
    result_row = await deps.jobs.get_result(existing.id)
    diagnostics_dict = result_row.diagnostics if result_row else {}
    records = result_row.records if result_row else []
    return ExtractionResponse(
        job_id=existing.id,
        status=existing.status,
        url=existing.url,
        instruction=existing.instruction,
        records=records,
        diagnostics=Diagnostics.model_validate(diagnostics_dict)
        if diagnostics_dict
        else Diagnostics(),
        message="cached_idempotent_response",
    )


async def _persist_artifacts(
    deps: Pipeline,
    job_id: str,
    plan: ExtractionPlan,
    report: ValidationReport,
    result: ExtractionResult,
    intent: IntentSchema,
) -> None:
    await deps.artifacts.write_json(job_id, "plan.json", plan.model_dump(mode="json"))
    await deps.artifacts.write_json(job_id, "validation.json", report.model_dump(mode="json"))
    await deps.artifacts.write_json(
        job_id, "result.json", {"records": result.records, "strategy": result.strategy_used}
    )
