"""users + org_memberships

Revision ID: 0002_users_memberships
Revises: 0001_baseline
Create Date: 2026-06-05

Phase 1.5 schema: multi-tenant user/membership graph on top of the Phase 1
baseline. `users` mirrors WorkOS users (one row per workos_user_id);
`org_memberships` is the bridge with a role enum (`owner` | `admin` | `member`)
that drives dashboard authorization. See MCP_SUBMISSION_PLAN.md s6.5.A.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_users_memberships"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("workos_user_id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workos_user_id", name="uq_users_workos_user_id"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "org_memberships",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            sa.BigInteger(),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "org_id", name="uq_org_memberships_user_org"),
        sa.CheckConstraint(
            "role IN ('owner','admin','member')",
            name="ck_org_memberships_role",
        ),
    )
    op.create_index("ix_org_memberships_user", "org_memberships", ["user_id"])
    op.create_index("ix_org_memberships_org", "org_memberships", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_org_memberships_org", table_name="org_memberships")
    op.drop_index("ix_org_memberships_user", table_name="org_memberships")
    op.drop_table("org_memberships")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
