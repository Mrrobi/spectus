"""init

Revision ID: 0001_init
Revises:
Create Date: 2026-05-17

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.sqlite import JSON

revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extraction_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("domain", sa.String(length=255), nullable=False, index=True),
        sa.Column("url_pattern", sa.String(length=512), nullable=False),
        sa.Column("goal_signature", sa.String(length=64), nullable=False, index=True),
        sa.Column("page_type", sa.String(length=64), nullable=True),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("extraction_plan", JSON(), nullable=False),
        sa.Column("success_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="candidate", index=True),
        sa.Column("consecutive_successes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_tpl_domain_goal",
        "extraction_templates",
        ["domain", "goal_signature"],
    )

    op.create_table(
        "extraction_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False, index=True),
        sa.Column("instruction", sa.String(length=2000), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True, index=True),
        sa.Column("status", sa.String(length=32), nullable=False, index=True),
        sa.Column("page_type", sa.String(length=64), nullable=True),
        sa.Column("strategy_used", sa.String(length=64), nullable=True),
        sa.Column("output_format", sa.String(length=16), nullable=False, server_default="json"),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("runtime_ms", sa.Integer(), nullable=True),
        sa.Column("repair_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "template_id",
            sa.Uuid(),
            sa.ForeignKey("extraction_templates.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "extraction_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("extraction_jobs.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("records", JSON(), nullable=False),
        sa.Column("diagnostics", JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "extraction_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("extraction_jobs.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("storage_url", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("extraction_artifacts")
    op.drop_table("extraction_results")
    op.drop_table("extraction_jobs")
    op.drop_index("ix_tpl_domain_goal", table_name="extraction_templates")
    op.drop_table("extraction_templates")
