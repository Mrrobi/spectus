from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from spectus._db.models import ExtractionArtifact, ExtractionJob, ExtractionResult, ExtractionTemplate


class JobRepo:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def create(
        self,
        *,
        url: str,
        domain: str,
        instruction: str,
        idempotency_key: str,
        output_format: str = "json",
    ) -> UUID:
        async with self._sm() as s:
            row = ExtractionJob(
                url=url,
                domain=domain,
                instruction=instruction,
                idempotency_key=idempotency_key,
                output_format=output_format,
                status="running",
            )
            s.add(row)
            await s.commit()
            return row.id

    async def find_by_idempotency_key(self, key: str) -> ExtractionJob | None:
        async with self._sm() as s:
            stmt = (
                select(ExtractionJob)
                .where(ExtractionJob.idempotency_key == key)
                .order_by(desc(ExtractionJob.created_at))
                .limit(1)
            )
            return (await s.execute(stmt)).scalar_one_or_none()

    async def get(self, job_id: UUID) -> ExtractionJob | None:
        async with self._sm() as s:
            return await s.get(ExtractionJob, job_id)

    async def update_status(self, job_id: UUID, **fields: Any) -> None:
        if not fields:
            return
        async with self._sm() as s:
            await s.execute(update(ExtractionJob).where(ExtractionJob.id == job_id).values(**fields))
            await s.commit()

    async def save_result(
        self, job_id: UUID, records: Any, diagnostics: dict[str, Any]
    ) -> None:
        async with self._sm() as s:
            s.add(ExtractionResult(job_id=job_id, records=records, diagnostics=diagnostics))
            await s.commit()

    async def get_result(self, job_id: UUID) -> ExtractionResult | None:
        async with self._sm() as s:
            stmt = (
                select(ExtractionResult)
                .where(ExtractionResult.job_id == job_id)
                .order_by(desc(ExtractionResult.created_at))
                .limit(1)
            )
            return (await s.execute(stmt)).scalar_one_or_none()


class TemplateRepo:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def find_candidates(
        self, domain: str, goal_signature: str
    ) -> list[ExtractionTemplate]:
        async with self._sm() as s:
            stmt = (
                select(ExtractionTemplate)
                .where(
                    ExtractionTemplate.domain == domain,
                    ExtractionTemplate.goal_signature == goal_signature,
                    ExtractionTemplate.status != "deprecated",
                )
                .order_by(
                    ExtractionTemplate.status,
                    desc(ExtractionTemplate.success_score),
                )
            )
            return list((await s.execute(stmt)).scalars().all())

    async def insert_candidate(
        self,
        *,
        domain: str,
        url_pattern: str,
        goal_signature: str,
        page_type: str | None,
        strategy: str,
        extraction_plan: dict[str, Any],
        success_score: float,
    ) -> UUID:
        async with self._sm() as s:
            row = ExtractionTemplate(
                domain=domain,
                url_pattern=url_pattern,
                goal_signature=goal_signature,
                page_type=page_type,
                strategy=strategy,
                extraction_plan=extraction_plan,
                success_score=success_score,
                status="candidate",
                consecutive_successes=1,
                consecutive_failures=0,
            )
            s.add(row)
            await s.commit()
            return row.id

    async def bump_success(self, template_id: UUID, score: float) -> None:
        async with self._sm() as s:
            row = await s.get(ExtractionTemplate, template_id)
            if row is None:
                return
            row.consecutive_successes += 1
            row.consecutive_failures = 0
            row.success_score = score
            row.last_used_at = datetime.now(timezone.utc)
            if row.status == "candidate" and row.consecutive_successes >= 3 and score >= 0.80:
                row.status = "active"
            elif row.status == "needs_review" and row.consecutive_successes >= 2:
                row.status = "active"
            await s.commit()

    async def bump_failure(self, template_id: UUID) -> None:
        async with self._sm() as s:
            row = await s.get(ExtractionTemplate, template_id)
            if row is None:
                return
            row.consecutive_failures += 1
            row.consecutive_successes = 0
            row.last_used_at = datetime.now(timezone.utc)
            if row.consecutive_failures >= 5:
                row.status = "deprecated"
            elif row.consecutive_failures >= 2 and row.status == "active":
                row.status = "needs_review"
            await s.commit()

    async def list_all(self, status: str | None = None) -> list[ExtractionTemplate]:
        async with self._sm() as s:
            stmt = select(ExtractionTemplate)
            if status is not None:
                stmt = stmt.where(ExtractionTemplate.status == status)
            stmt = stmt.order_by(desc(ExtractionTemplate.last_used_at))
            return list((await s.execute(stmt)).scalars().all())

    async def get(self, template_id: UUID) -> ExtractionTemplate | None:
        async with self._sm() as s:
            return await s.get(ExtractionTemplate, template_id)


class ArtifactRepo:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def record(self, job_id: UUID, artifact_type: str, storage_url: str) -> None:
        async with self._sm() as s:
            s.add(
                ExtractionArtifact(
                    job_id=job_id, artifact_type=artifact_type, storage_url=storage_url
                )
            )
            await s.commit()

    async def list_for_job(self, job_id: UUID) -> list[ExtractionArtifact]:
        async with self._sm() as s:
            stmt = select(ExtractionArtifact).where(ExtractionArtifact.job_id == job_id)
            return list((await s.execute(stmt)).scalars().all())
