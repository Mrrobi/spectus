from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from spectus._schemas.plan import ExtractionStrategy


class Diagnostics(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_used: ExtractionStrategy | None = None
    page_type: str | None = None
    static_or_browser: Literal["static", "browser"] | None = None
    records_found: int = 0
    quality_score: float | None = None
    field_coverage: dict[str, float] = Field(default_factory=dict)
    missing_required: dict[str, int] = Field(default_factory=dict)
    repair_attempts: int = 0
    template_used: bool = False
    template_id: UUID | None = None
    runtime_ms: int = 0
    llm_calls: int = 0
    llm_tokens_in: int = 0
    llm_tokens_out: int = 0
    warnings: list[str] = Field(default_factory=list)
