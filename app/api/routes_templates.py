from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.deps import Pipeline, get_pipeline
from app.schemas.template import Template

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[Template])
async def list_templates(
    status: str | None = None,
    deps: Pipeline = Depends(get_pipeline),
) -> list[Template]:
    return await deps.templates.list_all(status)


@router.get("/{template_id}", response_model=Template)
async def get_template(
    template_id: UUID,
    deps: Pipeline = Depends(get_pipeline),
) -> Template:
    t = await deps.templates.get(template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="not_found")
    return t
