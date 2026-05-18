"""LLM-driven extraction from a FactsBundle. No DOM selectors involved.

When invoked: a Pydantic record model is generated dynamically from the
user's IntentSchema, OpenAI Structured Outputs returns records matching
that schema, then values are normalized through FieldNormalizer.

Resilient to DOM shuffles because the input is text + labels + anchors +
structured data, not selectors.
"""
from __future__ import annotations

import json
from typing import Any, Type, get_args

from pydantic import BaseModel, ConfigDict, Field, create_model

from app.config import Settings
from app.errors import ExtractionPlanError, SchemaGenerationError
from app.llm.client import LlmClient
from app.llm.prompts import SEMANTIC_SYSTEM, SEMANTIC_USER_TEMPLATE
from app.schemas.bundle import FactsBundle
from app.schemas.execution import ExtractionResult, FieldStat
from app.schemas.intent import FieldType, IntentSchema
from app.services.normalizer import FieldNormalizer

_TYPE_MAP: dict[FieldType, Any] = {
    "string": str,
    "number": float,
    "integer": int,
    "currency": str,
    "url": str,
    "email": str,
    "phone": str,
    "date": str,
    "boolean": bool,
    "list_string": list[str],
}


def _record_model(intent: IntentSchema) -> Type[BaseModel]:
    fields_def: dict[str, Any] = {}
    for f in intent.fields:
        base = _TYPE_MAP[f.type]
        py_type = base | None
        desc = f.description or f"{f.name} ({f.type})"
        fields_def[f.name] = (py_type, Field(default=None, description=desc))
    Record = create_model(
        "SemanticRecord",
        __config__=ConfigDict(extra="forbid"),
        **fields_def,
    )
    return Record


def _envelope_model(intent: IntentSchema) -> Type[BaseModel]:
    Record = _record_model(intent)
    if intent.expected_output == "object":
        Envelope = create_model(
            "SemanticEnvelopeObject",
            __config__=ConfigDict(extra="forbid"),
            record=(Record | None, Field(default=None)),
            confidence=(float, Field(default=0.5)),
            notes=(str | None, Field(default=None)),
        )
    else:
        Envelope = create_model(
            "SemanticEnvelopeArray",
            __config__=ConfigDict(extra="forbid"),
            records=(list[Record], Field(default_factory=list)),
            confidence=(float, Field(default=0.5)),
            notes=(str | None, Field(default=None)),
        )
    return Envelope


class SemanticExtractor:
    def __init__(self, llm: LlmClient, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings
        self._normalizer = FieldNormalizer()

    async def extract(
        self,
        bundle: FactsBundle,
        intent: IntentSchema,
        instruction: str,
        *,
        job_id: str | None = None,
        artifact_writer: Any = None,
        max_records: int = 100,
    ) -> ExtractionResult:
        envelope_model = _envelope_model(intent)
        prompt_user = SEMANTIC_USER_TEMPLATE.format(
            instruction=instruction,
            schema_json=json.dumps(intent.model_dump(), ensure_ascii=False),
            bundle=bundle.to_prompt_text(),
            output_shape=intent.expected_output,
        )
        try:
            envelope = await self._llm.json_call(
                model=self._settings.openai_model_plan,
                system=SEMANTIC_SYSTEM,
                user=prompt_user,
                response_model=envelope_model,
                max_tokens=8000,
                timeout_s=self._settings.llm_planner_timeout_sec,
                temperature=0.0,
                job_id=job_id,
                step="semantic",
                artifact_writer=artifact_writer,
            )
        except SchemaGenerationError as e:
            raise ExtractionPlanError(detail=str(e)) from e

        records: list[dict[str, Any]] = []
        if intent.expected_output == "object":
            rec = getattr(envelope, "record", None)
            if rec is not None:
                records = [rec.model_dump(exclude_none=False)]
        else:
            raw_records = getattr(envelope, "records", []) or []
            records = [r.model_dump(exclude_none=False) for r in raw_records[:max_records]]

        stats: dict[str, FieldStat] = {f.name: FieldStat() for f in intent.fields}
        for rec in records:
            for f in intent.fields:
                raw = rec.get(f.name)
                if raw is None or raw == "" or raw == []:
                    stats[f.name] = FieldStat(
                        hits=stats[f.name].hits,
                        misses=stats[f.name].misses + 1,
                        errors=stats[f.name].errors,
                    )
                    rec[f.name] = None
                    continue
                try:
                    norm = self._normalizer.normalize(raw, f.type, bundle.url)
                except Exception:
                    stats[f.name] = FieldStat(
                        hits=stats[f.name].hits,
                        misses=stats[f.name].misses,
                        errors=stats[f.name].errors + 1,
                    )
                    continue
                if norm is None or norm == "":
                    stats[f.name] = FieldStat(
                        hits=stats[f.name].hits,
                        misses=stats[f.name].misses + 1,
                        errors=stats[f.name].errors,
                    )
                    rec[f.name] = None
                    continue
                rec[f.name] = norm
                stats[f.name] = FieldStat(
                    hits=stats[f.name].hits + 1,
                    misses=stats[f.name].misses,
                    errors=stats[f.name].errors,
                )

        records = [r for r in records if any(v not in (None, "", []) for v in r.values())]
        notes = []
        if getattr(envelope, "notes", None):
            notes.append(str(envelope.notes))
        return ExtractionResult(
            status="success" if records else "empty",
            strategy_used="semantic_extraction",
            records=records,
            field_diagnostics=stats,
            notes=notes,
        )
