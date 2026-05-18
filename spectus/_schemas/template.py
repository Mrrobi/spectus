from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from spectus._schemas.plan import ExtractionPlan, ExtractionStrategy

TemplateStatus = Literal["candidate", "active", "needs_review", "deprecated"]


class Template(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    domain: str
    url_pattern: str
    goal_signature: str
    page_type: str | None = None
    strategy: ExtractionStrategy
    plan: ExtractionPlan
    success_score: float
    status: TemplateStatus
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    created_at: datetime
    last_used_at: datetime | None = None
