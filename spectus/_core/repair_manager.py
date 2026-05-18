from __future__ import annotations

import json
from dataclasses import dataclass

from spectus._core.extraction_executor import ExtractionExecutor
from spectus._core.validator import Validator
from spectus._llm.client import LlmClient
from spectus._llm.prompts import REPAIR_SYSTEM, REPAIR_USER_TEMPLATE
from spectus._schemas.execution import ExtractionResult
from spectus._schemas.intent import IntentSchema
from spectus._schemas.page import CompactPage
from spectus._schemas.plan import ExtractionPlan
from spectus._schemas.validation import ValidationReport
from spectus.config import Settings
from spectus.errors import ExtractionPlanError, SchemaGenerationError


@dataclass(frozen=True)
class RepairContext:
    intent: IntentSchema
    prev_plan: ExtractionPlan
    prev_report: ValidationReport
    compact: CompactPage
    html: str
    base_url: str
    instruction: str
    max_records: int


class RepairManager:
    def __init__(
        self,
        llm: LlmClient,
        executor: ExtractionExecutor,
        validator: Validator,
        settings: Settings,
    ) -> None:
        self._llm = llm
        self._executor = executor
        self._validator = validator
        self._settings = settings

    async def repair_once(
        self,
        ctx: RepairContext,
        *,
        job_id: str | None = None,
        attempt: int = 1,
        artifact_writer=None,
    ) -> tuple[ExtractionPlan, ExtractionResult, ValidationReport]:
        try:
            new_plan = await self._llm.json_call(
                model=self._settings.openai_model_repair,
                system=REPAIR_SYSTEM,
                user=REPAIR_USER_TEMPLATE.format(
                    instruction=ctx.instruction,
                    schema_json=json.dumps(ctx.intent.model_dump(), ensure_ascii=False),
                    previous_plan_json=json.dumps(ctx.prev_plan.model_dump(), ensure_ascii=False),
                    validation_json=json.dumps(ctx.prev_report.model_dump(), ensure_ascii=False),
                    compact_json=json.dumps(
                        ctx.compact.model_dump(exclude_none=True), ensure_ascii=False
                    )[:8000],
                ),
                response_model=ExtractionPlan,
                max_tokens=6000,
                timeout_s=self._settings.llm_repair_timeout_sec,
                temperature=0.2,
                job_id=job_id,
                step=f"repair_{attempt}",
                artifact_writer=artifact_writer,
            )
        except SchemaGenerationError as e:
            raise ExtractionPlanError(detail=str(e)) from e
        new_result = self._executor.execute(
            new_plan, ctx.html, ctx.base_url, ctx.intent, ctx.max_records
        )
        new_report = self._validator.validate(new_result, ctx.intent, ctx.compact)
        return new_plan, new_result, new_report
