from __future__ import annotations

import json

from app.config import Settings
from app.errors import ExtractionPlanError, SchemaGenerationError
from app.llm.client import LlmClient
from app.llm.prompts import PLANNER_SYSTEM, PLANNER_USER_TEMPLATE
from app.schemas.intent import IntentSchema
from app.schemas.page import CompactPage
from app.schemas.plan import ExtractionPlan


class ExtractionPlanner:
    def __init__(self, llm: LlmClient, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings

    async def plan(
        self,
        instruction: str,
        schema: IntentSchema,
        compact: CompactPage,
        *,
        job_id: str | None = None,
        artifact_writer=None,
    ) -> ExtractionPlan:
        compact_json = _trim_compact(compact)
        try:
            return await self._llm.json_call(
                model=self._settings.openai_model_plan,
                system=PLANNER_SYSTEM,
                user=PLANNER_USER_TEMPLATE.format(
                    instruction=instruction,
                    schema_json=json.dumps(schema.model_dump(), ensure_ascii=False),
                    compact_json=compact_json,
                ),
                response_model=ExtractionPlan,
                max_tokens=6000,
                timeout_s=self._settings.llm_planner_timeout_sec,
                temperature=0.0,
                job_id=job_id,
                step="planner",
                artifact_writer=artifact_writer,
            )
        except SchemaGenerationError as e:
            raise ExtractionPlanError(detail=str(e)) from e


def _trim_compact(compact: CompactPage, budget_bytes: int = 8000) -> str:
    payload = compact.model_dump(mode="json", exclude_none=True)
    if "structured_data" in payload:
        sd = payload["structured_data"]
        if isinstance(sd.get("raw_payloads"), list):
            sd["raw_payloads"] = sd["raw_payloads"][:3]
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized) <= budget_bytes:
        return serialized
    trimmed = payload
    trimmed["links_sample"] = trimmed.get("links_sample", [])[:5]
    trimmed["tables"] = [
        {**t, "sample_rows": t.get("sample_rows", [])[:1]} for t in trimmed.get("tables", [])
    ][:3]
    trimmed["candidate_sections"] = [
        {**c, "sample_texts": [s[:120] for s in c.get("sample_texts", [])[:1]]}
        for c in trimmed.get("candidate_sections", [])
    ][:3]
    serialized = json.dumps(trimmed, ensure_ascii=False)
    if len(serialized) > budget_bytes:
        serialized = serialized[:budget_bytes] + '"}'
    return serialized
