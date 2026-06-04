"""baseline: orgs, api_keys, quotas, usage_events

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-04

Baseline schema for the auth + quota + metering layer (MCP_SUBMISSION_PLAN
Phase 1). Four tables; the fifth (stripe_customers / subscriptions) lands in
Phase 4 when paid billing turns on.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("workos_org_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False, server_default="free"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("workos_org_id", name="uq_orgs_workos_org_id"),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "org_id",
            sa.BigInteger(),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_org_id", "api_keys", ["org_id"])

    op.create_table(
        "quotas",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "org_id",
            sa.BigInteger(),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calls_remaining", sa.Integer(), nullable=False),
        sa.Column("calls_limit", sa.Integer(), nullable=False),
        sa.UniqueConstraint("org_id", "period_start", name="uq_quotas_org_period"),
        sa.CheckConstraint("calls_remaining >= 0", name="ck_quotas_calls_nonneg"),
    )
    op.create_index("ix_quotas_org_period", "quotas", ["org_id", "period_start"])

    op.create_table(
        "usage_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "org_id",
            sa.BigInteger(),
            sa.ForeignKey("orgs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "api_key_id",
            sa.BigInteger(),
            sa.ForeignKey("api_keys.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("auth_method", sa.String(length=16), nullable=False),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("cost_cents", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_usage_events_org_created", "usage_events", ["org_id", "created_at"]
    )
    op.create_index(
        "ix_usage_events_tool_created", "usage_events", ["tool", "created_at"]
    )
    op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_usage_events_created_at", table_name="usage_events")
    op.drop_index("ix_usage_events_tool_created", table_name="usage_events")
    op.drop_index("ix_usage_events_org_created", table_name="usage_events")
    op.drop_table("usage_events")

    op.drop_index("ix_quotas_org_period", table_name="quotas")
    op.drop_table("quotas")

    op.drop_index("ix_api_keys_org_id", table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_table("orgs")
