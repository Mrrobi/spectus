from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.deps import Pipeline, get_pipeline

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/metrics")
async def metrics(deps: Pipeline = Depends(get_pipeline)) -> dict:
    return deps.metrics.snapshot()
