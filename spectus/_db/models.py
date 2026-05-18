from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ExtractionJob(Base):
    __tablename__ = "extraction_jobs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    url: Mapped[str] = mapped_column(String(2048))
    domain: Mapped[str] = mapped_column(String(255), index=True)
    instruction: Mapped[str] = mapped_column(String(2000))
    idempotency_key: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    status: Mapped[str] = mapped_column(String(32), index=True)
    page_type: Mapped[str | None] = mapped_column(String(64), default=None)
    strategy_used: Mapped[str | None] = mapped_column(String(64), default=None)
    output_format: Mapped[str] = mapped_column(String(16), default="json")
    quality_score: Mapped[float | None] = mapped_column(default=None)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)
    error_message: Mapped[str | None] = mapped_column(String(2000), default=None)
    runtime_ms: Mapped[int | None] = mapped_column(default=None)
    repair_attempts: Mapped[int] = mapped_column(default=0)
    template_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("extraction_templates.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class ExtractionResult(Base):
    __tablename__ = "extraction_results"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("extraction_jobs.id"), index=True)
    records: Mapped[Any] = mapped_column(JSON)
    diagnostics: Mapped[Any] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ExtractionTemplate(Base):
    __tablename__ = "extraction_templates"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    url_pattern: Mapped[str] = mapped_column(String(512))
    goal_signature: Mapped[str] = mapped_column(String(64), index=True)
    page_type: Mapped[str | None] = mapped_column(String(64), default=None)
    strategy: Mapped[str] = mapped_column(String(64))
    extraction_plan: Mapped[Any] = mapped_column(JSON)
    success_score: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="candidate", index=True)
    consecutive_successes: Mapped[int] = mapped_column(default=0)
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        Index("ix_tpl_domain_goal", "domain", "goal_signature"),
    )


class ExtractionArtifact(Base):
    __tablename__ = "extraction_artifacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("extraction_jobs.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(64))
    storage_url: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
