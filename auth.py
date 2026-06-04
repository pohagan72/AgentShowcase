# auth.py
# Two-path auth + quota + metering. One decorator, one Principal, one ledger.
#
# Path A: OAuth bearer JWT (issued by WorkOS AuthKit) — used by Claude Desktop /
#   claude.ai over MCP.
# Path B: API key `sk_synzo_...` — used by paying customers from their own code.
#
# Both resolve to the same Principal(org_id, plan). Downstream logic (rate limit,
# quota decrement, metering, audit log) is shared. See MCP_SUBMISSION_PLAN.md s5.

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from typing import Callable

import jwt
from flask import current_app, g, jsonify, request
from jwt import PyJWKClient
from sqlalchemy import text as sql_text

from db import db
from db.models import ApiKey, Org, Quota, UsageEvent

logger = logging.getLogger(__name__)

API_KEY_PREFIX = "sk_synzo_"
API_KEY_RANDOM_BYTES = 32  # secrets.token_urlsafe(32) -> 256 bits of entropy

# Single source of truth for plans. Adding a tier is one line here.
PLANS: dict[str, dict[str, int]] = {
    "free":    {"calls_per_month": 50,      "pages_per_call": 20,  "rpm": 10},
    "starter": {"calls_per_month": 10_000,  "pages_per_call": 100, "rpm": 60},
    "pro":     {"calls_per_month": 100_000, "pages_per_call": 500, "rpm": 300},
}


@dataclass(frozen=True)
class Principal:
    org_id: int
    plan: str
    auth_method: str  # 'oauth' | 'api_key'
    api_key_id: int | None = None


class AuthError(Exception):
    """Raised inside resolvers; the decorator converts to a JSON 401."""

    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.message = message
        self.status = status


# --- WorkOS JWT verification ---------------------------------------------------
#
# JWKS is fetched once per process and cached by PyJWKClient. Cache is rebuilt
# on restart; that's fine until we run >1 replica, at which point each replica
# caches independently — still correct, just N fetches instead of 1.

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = os.environ.get("WORKOS_JWKS_URL")
        if not url:
            raise AuthError("OAuth not configured: WORKOS_JWKS_URL missing", status=500)
        _jwks_client = PyJWKClient(url, cache_keys=True, lifespan=3600)
    return _jwks_client


def _resolve_oauth(bearer_token: str) -> Principal:
    """Verify a WorkOS-issued JWT and resolve it to a Principal.

    Audience and issuer are pinned via env vars so a token meant for some other
    WorkOS application can't be replayed against us.
    """
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(bearer_token).key
    except jwt.PyJWKClientError as e:
        raise AuthError(f"Token signing key not found: {e}", status=401) from e
    except jwt.DecodeError as e:
        # Token isn't a well-formed JWT at all (e.g. random string). Treat as 401
        # rather than letting it bubble to a 500.
        raise AuthError("Malformed token", status=401) from e

    audience = os.environ.get("WORKOS_CLIENT_ID")
    issuer = os.environ.get("WORKOS_ISSUER")  # e.g. https://api.workos.com/user_management/<env_id>

    try:
        claims = jwt.decode(
            bearer_token,
            signing_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise AuthError("Token expired", status=401) from e
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Invalid token: {e}", status=401) from e

    workos_org_id = claims.get("org_id") or claims.get("organization_id")
    if not workos_org_id:
        raise AuthError("Token missing org_id claim", status=401)

    org = db.session.query(Org).filter_by(workos_org_id=workos_org_id).one_or_none()
    if org is None:
        raise AuthError("Org not provisioned", status=401)

    return Principal(org_id=org.id, plan=org.plan, auth_method="oauth")


# --- API key issuance + verification ------------------------------------------


def issue_api_key(org_id: int, name: str | None = None) -> tuple[str, ApiKey]:
    """Generate a new `sk_synzo_<32-url-bytes>` key, store its sha256 hash, return both.

    The raw key is returned to the caller exactly once. Only the hash is persisted.
    Use `secrets` (cryptographically secure) — never `random.*` or `uuid4`.
    """
    raw = API_KEY_PREFIX + secrets.token_urlsafe(API_KEY_RANDOM_BYTES)
    key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    record = ApiKey(
        org_id=org_id,
        key_hash=key_hash,
        prefix=raw[:16],
        name=name,
    )
    db.session.add(record)
    db.session.commit()
    return raw, record


def _resolve_api_key(raw_key: str) -> Principal:
    """Look up an API key by sha256 hash with constant-time comparison.

    The DB lookup is by hash equality (an indexed unique column), so a timing
    side channel via SQL is bounded by index probing. The Python-side check uses
    `hmac.compare_digest` to avoid `==`'s short-circuit on hash strings.
    """
    if not raw_key.startswith(API_KEY_PREFIX):
        raise AuthError("Malformed API key", status=401)

    computed = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    record = db.session.query(ApiKey).filter_by(key_hash=computed).one_or_none()
    if record is None:
        # Still spend a constant-time compare against a sentinel so the failure
        # path doesn't return measurably faster than the success path.
        hmac.compare_digest(computed, "0" * 64)
        raise AuthError("Invalid API key", status=401)

    if not hmac.compare_digest(record.key_hash, computed):
        # Belt-and-braces: SQL equality already matched, but compare again with
        # a timing-safe primitive in case a future change loosens the lookup.
        raise AuthError("Invalid API key", status=401)

    if record.revoked_at is not None:
        raise AuthError("API key revoked", status=401)

    org = db.session.get(Org, record.org_id)
    if org is None:
        raise AuthError("Org not found", status=401)

    record.last_used_at = datetime.now(timezone.utc)
    db.session.commit()

    return Principal(
        org_id=org.id,
        plan=org.plan,
        auth_method="api_key",
        api_key_id=record.id,
    )


# --- Quota: atomic decrement ---------------------------------------------------
#
# Single UPDATE ... RETURNING. Races between concurrent callers are resolved by
# the row lock; the WHERE clause guarantees we never decrement below zero. The
# matching period row must already exist (provisioned on org creation / plan
# change). If it doesn't, the call is 402'd rather than implicitly creating one.


def _period_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _decrement_quota(org_id: int) -> bool:
    """Atomically decrement `calls_remaining` for the current period.

    Returns True on success, False if exhausted or no period row exists.
    """
    now = datetime.now(timezone.utc)
    period_start, _ = _period_bounds(now)
    result = db.session.execute(
        sql_text(
            """
            UPDATE quotas
               SET calls_remaining = calls_remaining - 1
             WHERE org_id = :org_id
               AND period_start = :period_start
               AND calls_remaining > 0
            RETURNING id
            """
        ),
        {"org_id": org_id, "period_start": period_start},
    ).first()
    db.session.commit()
    return result is not None


def _refund_quota(org_id: int) -> None:
    now = datetime.now(timezone.utc)
    period_start, _ = _period_bounds(now)
    db.session.execute(
        sql_text(
            """
            UPDATE quotas
               SET calls_remaining = calls_remaining + 1
             WHERE org_id = :org_id
               AND period_start = :period_start
               AND calls_remaining < calls_limit
            """
        ),
        {"org_id": org_id, "period_start": period_start},
    )
    db.session.commit()


def _record_usage(
    principal: Principal,
    tool: str,
    units: int,
    status: str,
    error_code: str | None = None,
) -> None:
    """Append-only insert into usage_events. Never store prompt/document bodies."""
    event = UsageEvent(
        org_id=principal.org_id,
        api_key_id=principal.api_key_id,
        auth_method=principal.auth_method,
        tool=tool,
        units=units,
        status=status,
        error_code=error_code,
    )
    db.session.add(event)
    db.session.commit()


# --- Rate limit (per-org-per-minute) ------------------------------------------
#
# In-memory fallback until Redis lands (plan s4 ring 1). Per-org RPM is the
# minimum useful axis — IP limits already live in extensions.py. When Redis is
# enabled, swap this for a Flask-Limiter call keyed on principal.org_id.

_rpm_buckets: dict[int, list[float]] = {}


def _check_rpm(principal: Principal) -> bool:
    plan = PLANS.get(principal.plan, PLANS["free"])
    limit = plan["rpm"]
    now = time.monotonic()
    window_start = now - 60.0
    bucket = _rpm_buckets.setdefault(principal.org_id, [])
    # Drop stamps older than 60s.
    while bucket and bucket[0] < window_start:
        bucket.pop(0)
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


# --- The decorator -------------------------------------------------------------


def _identify_principal() -> Principal:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer ") :].strip()
        if token.startswith(API_KEY_PREFIX):
            return _resolve_api_key(token)
        return _resolve_oauth(token)

    api_key_header = request.headers.get("X-API-Key", "").strip()
    if api_key_header:
        return _resolve_api_key(api_key_header)

    raise AuthError("Missing Authorization header", status=401)


def _json_error(message: str, status: int):
    return jsonify({"error": message}), status


def require_auth(
    tool_name: str,
    units_fn: Callable[..., int] | None = None,
):
    """Authenticate, rate-limit, decrement quota, run handler, meter.

    Order matches MCP_SUBMISSION_PLAN.md s5:
      1. Identify caller (OAuth JWT or API key).
      2. Reject if units > plan's per-call cap (413).
      3. Per-org-per-minute rate limit (429).
      4. Atomic quota decrement (402).
      5. Run handler.
      6. On error: refund quota.
      7. Always: insert into usage_events.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                principal = _identify_principal()
            except AuthError as e:
                return _json_error(e.message, e.status)

            g.principal = principal

            units = 1
            if units_fn is not None:
                try:
                    units = int(units_fn(request))
                except Exception as e:
                    logger.warning("units_fn failed for %s: %s", tool_name, e)
                    return _json_error("Could not size request", 400)

            plan = PLANS.get(principal.plan, PLANS["free"])
            if units > plan["pages_per_call"]:
                _record_usage(principal, tool_name, units, "error", "units_exceeded")
                return _json_error(
                    f"Request exceeds per-call limit ({plan['pages_per_call']} units)",
                    413,
                )

            if not _check_rpm(principal):
                _record_usage(principal, tool_name, units, "error", "rate_limited")
                return _json_error("Rate limit exceeded", 429)

            if not _decrement_quota(principal.org_id):
                _record_usage(principal, tool_name, units, "error", "quota_exhausted")
                return _json_error("Quota exhausted for this period", 402)

            try:
                response = fn(*args, **kwargs)
            except Exception:
                _refund_quota(principal.org_id)
                _record_usage(principal, tool_name, units, "refunded", "handler_error")
                raise

            _record_usage(principal, tool_name, units, "ok")
            return response

        return wrapper

    return decorator
