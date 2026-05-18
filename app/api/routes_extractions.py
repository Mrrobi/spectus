from __future__ import annotations

import asyncio
from time import monotonic
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse

from app.deps import Pipeline, get_pipeline
from app.errors import BudgetExceededError, JobTimeoutError
from app.logging import get_logger
from app.schemas.api import ExtractionRequest, ExtractionResponse
from app.schemas.diagnostics import Diagnostics
from app.services.exporter import records_to_csv
from app.services.orchestrator import run_extraction

router = APIRouter(prefix="/extractions", tags=["extractions"])


@router.post("", response_model=ExtractionResponse)
async def create_extraction(
    req: ExtractionRequest,
    deps: Pipeline = Depends(get_pipeline),
) -> ExtractionResponse:
    log = get_logger("api")
    started = monotonic()
    try:
        return await asyncio.wait_for(
            run_extraction(req, deps),
            timeout=deps.settings.job_deadline_sec + 2.0,
        )
    except asyncio.TimeoutError as e:
        log.warning("api_timeout", url=str(req.url))
        raise JobTimeoutError(detail="overall_timeout") from e
    except BudgetExceededError as e:
        elapsed_ms = int((monotonic() - started) * 1000)
        return ExtractionResponse(
            job_id=UUID(int=0),
            status="partial_success",
            url=str(req.url),
            instruction=req.instruction,
            records=None,
            diagnostics=Diagnostics(runtime_ms=elapsed_ms),
            message=e.user_message(),
        )


@router.get("/{job_id}", response_model=ExtractionResponse)
async def get_extraction(
    job_id: UUID,
    deps: Pipeline = Depends(get_pipeline),
) -> ExtractionResponse:
    job = await deps.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    result = await deps.jobs.get_result(job_id)
    records = result.records if result else None
    diagnostics_payload = result.diagnostics if result else {}
    return ExtractionResponse(
        job_id=job.id,
        status=job.status,  # type: ignore[arg-type]
        url=job.url,
        instruction=job.instruction,
        records=records,
        diagnostics=Diagnostics.model_validate(diagnostics_payload) if diagnostics_payload else Diagnostics(),
        message=None,
    )


@router.get("/{job_id}/export.csv")
async def export_csv(
    job_id: UUID,
    deps: Pipeline = Depends(get_pipeline),
) -> Response:
    result = await deps.jobs.get_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="not_found")
    records = result.records or []
    if isinstance(records, dict):
        records = [records]
    csv_text = records_to_csv(records)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="extraction_{job_id}.csv"'},
    )
