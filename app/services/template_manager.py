from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from fnmatch import fnmatch
from urllib.parse import urlparse
from uuid import UUID

from app.db.models import ExtractionTemplate
from app.db.repositories import TemplateRepo
from app.schemas.intent import IntentSchema
from app.schemas.plan import ExtractionPlan
from app.schemas.template import Template


def goal_signature(schema: IntentSchema) -> str:
    names = sorted({_norm_name(f.name) for f in schema.fields})
    return hashlib.sha256("|".join(names).encode("utf-8")).hexdigest()[:16]


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


_NUMERIC_LIKE_RE = re.compile(r"^[a-f0-9]{8,}$")


def url_pattern_glob(url: str) -> str:
    path = urlparse(url).path or "/"
    parts = path.split("/")
    out: list[str] = []
    for p in parts:
        if not p:
            out.append(p)
            continue
        if (
            p.isdigit()
            or len(p) > 30
            or _NUMERIC_LIKE_RE.match(p)
            or ("-" in p and any(c.isdigit() for c in p))
        ):
            out.append("*")
        else:
            out.append(p)
    return "/".join(out) or "/"


def _row_to_model(row: ExtractionTemplate) -> Template:
    return Template(
        id=row.id,
        domain=row.domain,
        url_pattern=row.url_pattern,
        goal_signature=row.goal_signature,
        page_type=row.page_type,
        strategy=row.strategy,  # type: ignore[arg-type]
        plan=ExtractionPlan.model_validate(row.extraction_plan),
        success_score=row.success_score,
        status=row.status,  # type: ignore[arg-type]
        consecutive_successes=row.consecutive_successes,
        consecutive_failures=row.consecutive_failures,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
    )


class TemplateManager:
    def __init__(self, repo: TemplateRepo) -> None:
        self._repo = repo

    async def find(self, domain: str, url: str, schema: IntentSchema) -> Template | None:
        sig = goal_signature(schema)
        path = urlparse(url).path or "/"
        rows = await self._repo.find_candidates(domain, sig)
        for row in rows:
            if fnmatch(path, row.url_pattern):
                return _row_to_model(row)
        return None

    async def record_new_candidate(
        self,
        *,
        domain: str,
        url: str,
        schema: IntentSchema,
        page_type: str | None,
        plan: ExtractionPlan,
        score: float,
    ) -> UUID:
        return await self._repo.insert_candidate(
            domain=domain,
            url_pattern=url_pattern_glob(url),
            goal_signature=goal_signature(schema),
            page_type=page_type,
            strategy=plan.strategy,
            extraction_plan=plan.model_dump(),
            success_score=score,
        )

    async def record_success(self, template_id: UUID, score: float) -> None:
        await self._repo.bump_success(template_id, score)

    async def record_failure(self, template_id: UUID) -> None:
        await self._repo.bump_failure(template_id)

    async def list_all(self, status: str | None = None) -> list[Template]:
        rows = await self._repo.list_all(status)
        return [_row_to_model(r) for r in rows]

    async def get(self, template_id: UUID) -> Template | None:
        row = await self._repo.get(template_id)
        return _row_to_model(row) if row else None
