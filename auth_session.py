# auth_session.py
# Session-cookie auth for the dashboard surface.
#
# The /api/v1/* surface uses Bearer tokens and the @require_auth decorator in
# auth.py. The /dashboard/* surface uses a Flask session cookie set on
# /auth/callback after WorkOS sign-in. Both surfaces resolve to a Principal so
# downstream tenant-scoping logic is identical.
#
# Role ordering: owner > admin > member. require_role enforces a minimum.

from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import g, redirect, request, session, url_for

from db import db
from db.models import Org, OrgMembership
from auth import Principal


# Higher number = more authority. Used by require_role to compare against
# the minimum required role.
_ROLE_RANK: dict[str, int] = {"member": 1, "admin": 2, "owner": 3}


def current_principal() -> Principal | None:
    """Read the Flask session, return a session-authed Principal or None.

    Returns None if the session is missing, points at an org the user is no
    longer a member of (e.g. they were removed in another tab), or references
    an org row that has since been deleted. Callers should treat None as
    "force re-login."
    """
    user_id = session.get("user_id")
    org_id = session.get("current_org_id")
    if not user_id or not org_id:
        return None

    membership = (
        db.session.query(OrgMembership)
        .filter_by(user_id=user_id, org_id=org_id)
        .one_or_none()
    )
    if membership is None:
        return None

    org = db.session.get(Org, org_id)
    if org is None:
        return None

    return Principal(
        org_id=org.id,
        plan=org.plan,
        auth_method="session",
        api_key_id=None,
        user_id=user_id,
        role=membership.role,
    )


def require_session(fn: Callable) -> Callable:
    """Dashboard decorator. If no valid session, redirect to /auth/login.

    On success attaches the Principal to flask.g so the view can read
    g.principal.org_id without re-querying.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        principal = current_principal()
        if principal is None:
            # Clear any partial/stale session so the next attempt starts
            # cleanly. The login route will set fresh keys.
            session.clear()
            # Preserve the requested URL so /auth/callback can bounce back to
            # it (set via the `next` query param the login route understands).
            return redirect(url_for("auth.login", next=request.path))
        g.principal = principal
        return fn(*args, **kwargs)

    return wrapper


def require_role(min_role: str) -> Callable:
    """Decorator factory: assert g.principal.role ranks >= min_role.

    Must be applied AFTER require_session so g.principal is populated. Returns
    a plain 403 (HTML) — dashboard routes are human-facing, not JSON.
    """
    if min_role not in _ROLE_RANK:
        raise ValueError(f"Unknown role: {min_role!r}")
    required_rank = _ROLE_RANK[min_role]

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            principal = getattr(g, "principal", None)
            if principal is None or principal.role is None:
                # require_session should have set this; if it didn't, refuse.
                return ("Forbidden", 403)
            actual_rank = _ROLE_RANK.get(principal.role, 0)
            if actual_rank < required_rank:
                return ("Forbidden", 403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator
