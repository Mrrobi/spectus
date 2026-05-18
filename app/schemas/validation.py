from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    overall_score: float = Field(ge=0.0, le=1.0)
    record_count_score: float = Field(ge=0.0, le=1.0)
    field_coverage_score: float = Field(ge=0.0, le=1.0)
    type_validity_score: float = Field(ge=0.0, le=1.0)
    duplication_score: float = Field(ge=0.0, le=1.0)
    missing_required: dict[str, int] = Field(default_factory=dict)
    missing_optional: dict[str, int] = Field(default_factory=dict)
    invalid_types: dict[str, int] = Field(default_factory=dict)
    duplicate_count: int = 0
    needs_repair: bool = False
    repair_hint: str | None = None
    good_enough: bool = False
