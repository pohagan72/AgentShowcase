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

import concurrent.futures
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
from flask import copy_current_request_context, current_app, g, has_request_context, jsonify, request
from jwt import PyJWKClient
from sqlalchemy import text as sql_text

from db import db
from db.models import ApiKey, Org, OrgMembership, Quota, UsageEvent, User

logger = logging.getLogger(__name__)

API_KEY_PREFIX = "sk_synzo_"
API_KEY_RANDOM_BYTES = 32  # secrets.token_urlsafe(32) -> 256 bits of entropy

# Wall-clock timeout for a single metered tool invocation. CPython can't force-
# kill the worker thread, so a runaway handler still occupies a thread until its
# downstream call (Gemini HTTPS, file I/O) unblocks naturally. What the timeout
# DOES guarantee: the caller gets a timely 504, the quota is refunded, the
# usage event is recorded as 'refunded'/'timeout', and Waitress' worker thread
# is freed to handle other requests. Tuneable via env so a misbehaving Gemini
# day doesn't require a code change. Set to 0 to disable.
TOOL_TIMEOUT_SECONDS = int(os.environ.get("MCP_TOOL_TIMEOUT_SECONDS", "60"))

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
    auth_method: str  # 'oauth' | 'api_key' | 'session'
    api_key_id: int | None = None
    # user_id is populated for 'session' callers (dashboard) and for 'oauth'
    # callers whose JWT carried a `sub` claim. 'api_key' callers stay None —
    # API keys belong to orgs, not users.
    user_id: int | None = None
    # role is set only for 'session' callers; it gates dashboard actions
    # (require_role). 'oauth' / 'api_key' callers stay None — those paths
    # don't pass through the dashboard auth gate.
    role: str | None = None


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
            logger.error("oauth_config_error: WORKOS_JWKS_URL env var is missing")
            raise AuthError("OAuth not configured: WORKOS_JWKS_URL missing", status=500)
        logger.info("oauth_config: initializing PyJWKClient url=%s", url)
        _jwks_client = PyJWKClient(url, cache_keys=True, lifespan=3600)
    return _jwks_client


def _resolve_oauth(bearer_token: str) -> Principal:
    """Verify a WorkOS-issued JWT and resolve it to a Principal.

    Audience and issuer are pinned via env vars so a token meant for some other
    WorkOS application can't be replayed against us.
    """
    token_prefix = bearer_token[:12] if bearer_token else "<empty>"
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(bearer_token).key
    except jwt.PyJWKClientError as e:
        logger.warning("oauth_reject: reason='signing_key_not_found' token_prefix=%s err=%s", token_prefix, e)
        raise AuthError(f"Token signing key not found: {e}", status=401) from e
    except jwt.DecodeError as e:
        # Token isn't a well-formed JWT at all (e.g. random string). Treat as 401
        # rather than letting it bubble to a 500.
        logger.warning("oauth_reject: reason='malformed_token' token_prefix=%s err=%s", token_prefix, e)
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
        logger.warning("oauth_reject: reason='expired' token_prefix=%s", token_prefix)
        raise AuthError("Token expired", status=401) from e
    except jwt.InvalidTokenError as e:
        # Catches: InvalidAudienceError, InvalidIssuerError, MissingRequiredClaimError, etc.
        # The exception type name tells us *which* validation failed.
        logger.warning(
            "oauth_reject: reason='invalid_token' token_prefix=%s err_type=%s err=%s "
            "expected_audience=%s expected_issuer=%s",
            token_prefix, type(e).__name__, e, audience, issuer,
        )
        raise AuthError(f"Invalid token: {e}", status=401) from e

    workos_user_id = claims.get("sub")
    workos_org_id = claims.get("org_id") or claims.get("organization_id")
    claim_keys = sorted(claims.keys())

    if not workos_org_id:
        logger.warning(
            "oauth_reject: reason='missing_org_id_claim' token_prefix=%s workos_user_id=%s "
            "email=%s claim_keys=%s",
            token_prefix, workos_user_id, claims.get("email"), claim_keys,
        )
        raise AuthError("Token missing org_id claim", status=401)

    org = db.session.query(Org).filter_by(workos_org_id=workos_org_id).one_or_none()
    if org is None:
        logger.warning(
            "oauth_reject: reason='org_not_provisioned' token_prefix=%s workos_user_id=%s "
            "workos_org_id=%s email=%s",
            token_prefix, workos_user_id, workos_org_id, claims.get("email"),
        )
        raise AuthError("Org not provisioned", status=401)

    # Upsert User + OrgMembership so OAuth callers (Claude Desktop / claude.ai
    # over MCP) populate the membership graph the same way browser callers do.
    # API-key callers don't have a user concept and skip this entirely.
    # (workos_user_id already pulled above so the reject logs can reference it.)
    user_id: int | None = None
    if workos_user_id:
        user = (
            db.session.query(User)
            .filter_by(workos_user_id=workos_user_id)
            .one_or_none()
        )
        if user is None:
            user = User(
                workos_user_id=workos_user_id,
                email=claims.get("email", "<unknown>"),
            )
            db.session.add(user)
            db.session.flush()
        membership = (
            db.session.query(OrgMembership)
            .filter_by(user_id=user.id, org_id=org.id)
            .one_or_none()
        )
        if membership is None:
            db.session.add(
                OrgMembership(user_id=user.id, org_id=org.id, role="member")
            )
        user.last_seen_at = datetime.now(timezone.utc)
        db.session.commit()
        user_id = user.id

    logger.info(
        "oauth_ok: org_id=%s plan=%s workos_org_id=%s workos_user_id=%s user_id=%s",
        org.id, org.plan, workos_org_id, workos_user_id, user_id,
    )
    return Principal(
        org_id=org.id,
        plan=org.plan,
        auth_method="oauth",
        user_id=user_id,
    )


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

    Period match is a range (`period_start <= now < period_end`) rather than an
    exact equality on `period_start`. Equality looks tidier but breaks on
    SQLite-backed test runs where TIMESTAMP WITH TIME ZONE round-trips through
    a tz-naive string and never matches. The range form is also what we
    semantically mean — "the quota row that covers right now."
    """
    now = datetime.now(timezone.utc)
    result = db.session.execute(
        sql_text(
            """
            UPDATE quotas
               SET calls_remaining = calls_remaining - 1
             WHERE org_id = :org_id
               AND period_start <= :now
               AND period_end > :now
               AND calls_remaining > 0
            RETURNING id
            """
        ),
        {"org_id": org_id, "now": now},
    ).first()
    db.session.commit()
    return result is not None


def _refund_quota(org_id: int) -> None:
    now = datetime.now(timezone.utc)
    db.session.execute(
        sql_text(
            """
            UPDATE quotas
               SET calls_remaining = calls_remaining + 1
             WHERE org_id = :org_id
               AND period_start <= :now
               AND period_end > :now
               AND calls_remaining < calls_limit
            """
        ),
        {"org_id": org_id, "now": now},
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
    x_api_key = request.headers.get("X-API-Key", "").strip()
    ua = request.headers.get("User-Agent", "<none>")[:120]
    origin = request.headers.get("Origin", "<none>")

    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer ") :].strip()
        if token.startswith(API_KEY_PREFIX):
            logger.info("auth_identify: path=api_key_bearer ua=%s origin=%s", ua, origin)
            return _resolve_api_key(token)
        logger.info(
            "auth_identify: path=oauth token_prefix=%s ua=%s origin=%s",
            token[:12] if token else "<empty>", ua, origin,
        )
        return _resolve_oauth(token)

    if x_api_key:
        logger.info("auth_identify: path=x_api_key_header ua=%s origin=%s", ua, origin)
        return _resolve_api_key(x_api_key)

    logger.warning(
        "auth_identify: path=none reason='missing_authorization' ua=%s origin=%s",
        ua, origin,
    )
    raise AuthError("Missing Authorization header", status=401)


def _json_error(message: str, status: int):
    return jsonify({"error": message}), status


def run_metered_tool(
    principal: Principal,
    tool_name: str,
    units: int,
    fn: Callable[[], object],
) -> object:
    """Run a tool through the quota/rate-limit/metering pipeline without HTTP.

    Same step ordering as require_auth (s5 of MCP_SUBMISSION_PLAN.md) minus the
    identify-caller step (the caller already has a Principal in hand) and minus
    the JSON-response translation (raises AuthError instead). MCP tool handlers
    use this so JSON-RPC error envelopes can be built at the protocol layer.

      1. Reject if units > plan's per-call cap (raises AuthError 413).
      2. Per-org-per-minute rate limit (raises AuthError 429).
      3. Atomic quota decrement (raises AuthError 402).
      4. Run fn().
      5. On error: refund quota, meter as 'refunded', re-raise.
      6. Success: meter as 'ok', return fn's result.
    """
    plan = PLANS.get(principal.plan, PLANS["free"])
    if units > plan["pages_per_call"]:
        _record_usage(principal, tool_name, units, "error", "units_exceeded")
        raise AuthError(
            f"Request exceeds per-call limit ({plan['pages_per_call']} units)",
            status=413,
        )

    if not _check_rpm(principal):
        _record_usage(principal, tool_name, units, "error", "rate_limited")
        raise AuthError(
            f"Rate limit exceeded ({plan['rpm']} requests/min)",
            status=429,
        )

    if not _decrement_quota(principal.org_id):
        _record_usage(principal, tool_name, units, "error", "quota_exhausted")
        raise AuthError("Quota exhausted for this period", status=402)

    try:
        result = _run_with_timeout(fn)
    except concurrent.futures.TimeoutError:
        _refund_quota(principal.org_id)
        _record_usage(principal, tool_name, units, "refunded", "timeout")
        raise AuthError(
            f"Tool execution exceeded {TOOL_TIMEOUT_SECONDS}s timeout",
            status=504,
        )
    except Exception:
        _refund_quota(principal.org_id)
        _record_usage(principal, tool_name, units, "refunded", "handler_error")
        raise

    _record_usage(principal, tool_name, units, "ok")
    return result


def _run_with_timeout(fn: Callable[[], object]) -> object:
    """Run fn on a worker thread, blocking the caller up to TOOL_TIMEOUT_SECONDS.

    Both Flask app context AND request context are propagated to the worker
    thread. Tool handlers in mcp_tools.py read current_app.config; route
    handlers (e.g. /api/v1/summarize) read request.files. Both need to work
    after we move the call onto another thread.

    On timeout, the Future is abandoned and the worker thread keeps running
    until fn returns naturally — CPython can't force-kill threads. The
    downstream Gemini HTTPS call has its own socket timeout that bounds the
    leak.

    If TOOL_TIMEOUT_SECONDS is 0 we run inline — no executor overhead. Tests
    use this so the harness doesn't pay a thread-spawn per trivially-fast
    stubbed handler.
    """
    if TOOL_TIMEOUT_SECONDS <= 0:
        return fn()

    # copy_current_request_context binds both app and request context onto
    # whichever thread eventually calls _runner. It MUST be invoked while a
    # request context is active (we are — every caller of run_metered_tool is
    # inside a Flask route). Fall back to app-context-only if for some reason
    # we're not (e.g. a future background-job caller).
    if has_request_context():
        _runner = copy_current_request_context(fn)
    else:
        app = current_app._get_current_object()

        def _runner():  # type: ignore[no-redef]
            with app.app_context():
                return fn()

    # Don't use ThreadPoolExecutor as a context manager — its __exit__ joins
    # the worker thread, which negates the timeout (we'd block waiting for the
    # runaway handler to finish before raising). Construct manually, shut down
    # without waiting on timeout, let the thread leak to its natural end.
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(_runner)
        try:
            return future.result(timeout=TOOL_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            # Don't join the worker. Gemini's HTTPS timeout bounds the leak.
            pool.shutdown(wait=False)
            raise
    finally:
        # On the happy path / non-timeout error path, this joins (worker has
        # already finished). On timeout we already called shutdown(wait=False).
        pool.shutdown(wait=False)


def require_auth(
    tool_name: str,
    units_fn: Callable[..., int] | None = None,
):
    """HTTP adapter around run_metered_tool. Returns Flask JSON responses for
    the 401/402/413/429 paths. The MCP layer uses run_metered_tool directly so
    it can wrap errors in JSON-RPC envelopes instead.

    Order matches MCP_SUBMISSION_PLAN.md s5.
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

            try:
                return run_metered_tool(principal, tool_name, units, lambda: fn(*args, **kwargs))
            except AuthError as e:
                return _json_error(e.message, e.status)

        return wrapper

    return decorator
