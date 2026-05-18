from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from spectus._schemas.plan import ExtractionStrategy


class FieldStat(BaseModel):
    model_config = ConfigDict(frozen=True)

    hits: int = 0
    misses: int = 0
    errors: int = 0


class ExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["success", "partial", "empty"]
    strategy_used: ExtractionStrategy
    records: list[dict[str, Any]] = Field(default_factory=list)
    field_diagnostics: dict[str, FieldStat] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class FetchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    final_url: str
    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)
    html: str
    elapsed_ms: int
    content_type: str


class RenderResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    final_url: str
    html: str
    screenshot_path: str | None = None
    elapsed_ms: int
    visible_text_length: int
