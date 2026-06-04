# db/models.py
# Schema for the auth + quota + metering layer (Phase 1 of MCP_SUBMISSION_PLAN).
#
# Five tables back the two-path auth model (OAuth bearer JWT for MCP, sk_synzo_
# API keys for paid customers). Both resolve to the same Principal (org_id +
# plan). quotas drives atomic per-call decrement; usage_events is the
# append-only billing source of truth.
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Org(db.Model):
    """One row per customer (human signup or paying org).

    `plan` is a free-text key into the PLANS dict in auth.py. Storing the
    string (not a FK) keeps adding a tier to one line of code.
    """

    __tablename__ = "orgs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workos_org_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="org", cascade="all, delete-orphan")
    quotas: Mapped[list["Quota"]] = relationship(back_populates="org", cascade="all, delete-orphan")
    usage_events: Mapped[list["UsageEvent"]] = relationship(back_populates="org")


class ApiKey(db.Model):
    """Hashed sk_synzo_... API keys, revocable, one org -> many keys.

    Raw key shown to the customer once at issuance. Only sha256 hash stored.
    `prefix` is the first 16 chars of the raw key, kept plaintext so customers
    can identify which key is which in their dashboard. `revoked_at` is set
    instead of deleting — keeps usage_events FK references intact.
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    org: Mapped["Org"] = relationship(back_populates="api_keys")


class Quota(db.Model):
    """Current period's remaining calls, decremented atomically.

    One row per (org, period). `period_start` is the UTC midnight of the first
    day of the billing period; `period_end` is exclusive. The decorator runs
    a single UPDATE ... RETURNING against `calls_remaining` to avoid races
    under concurrent requests.
    """

    __tablename__ = "quotas"
    __table_args__ = (
        UniqueConstraint("org_id", "period_start", name="uq_quotas_org_period"),
        CheckConstraint("calls_remaining >= 0", name="ck_quotas_calls_nonneg"),
        Index("ix_quotas_org_period", "org_id", "period_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    calls_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    calls_limit: Mapped[int] = mapped_column(Integer, nullable=False)

    org: Mapped["Org"] = relationship(back_populates="quotas")


class UsageEvent(db.Model):
    """Append-only audit log + billing source of truth.

    Never deleted. Records who called what tool, how many units, success or
    failure, and the (eventual) cost. Privacy review evidence — never store
    document or prompt contents here, only metadata.
    """

    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_org_created", "org_id", "created_at"),
        Index("ix_usage_events_tool_created", "tool", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orgs.id", ondelete="RESTRICT"), nullable=False
    )
    api_key_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
    )
    auth_method: Mapped[str] = mapped_column(String(16), nullable=False)  # 'oauth' | 'api_key'
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # 'ok' | 'error' | 'refunded'
    cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )

    org: Mapped["Org"] = relationship(back_populates="usage_events")


