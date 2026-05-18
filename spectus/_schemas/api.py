from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from spectus._schemas.diagnostics import Diagnostics


class ExtractionOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_browser: Literal["auto", "force", "never"] = "auto"
    max_records: int = Field(default=100, ge=1, le=1000)
    save_template: bool = True


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    instruction: str = Field(min_length=3, max_length=1000)
    output_format: Literal["json", "csv"] = "json"
    options: ExtractionOptions = Field(default_factory=ExtractionOptions)


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: UUID
    status: Literal["success", "partial_success", "failed"]
    url: str
    instruction: str
    records: list[dict[str, Any]] | dict[str, Any] | None = None
    diagnostics: Diagnostics
    message: str | None = None
