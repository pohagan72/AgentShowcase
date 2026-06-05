# auth_routes.py
# /auth/* sign-in/-up/-out via WorkOS AuthKit, plus the /dashboard/* surface.
# See MCP_SUBMISSION_PLAN.md s6.5.C.
#
# Surface contract (plan s3.3):
#   - These routes are cookie-session-authenticated, not Bearer-authenticated.
#   - Never use @require_auth here — it returns JSON 401 which breaks the HTML
#     redirect-to-login flow. Use @require_session (auth_session.py) instead.
#   - CSRF protection (Flask-WTF) is left ON for this blueprint — these are
#     human-driven cookie sessions exactly like the public HTMX routes.

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse

import jwt
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from workos import WorkOSClient

from auth import PLANS, _period_bounds, issue_api_key
from auth_session import require_role, require_session
from db import db
from db.models import ApiKey, Org, OrgMembership, Quota, User

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__)


# --- WorkOS client (lazy) -----------------------------------------------------


_workos_client: WorkOSClient | None = None


def _workos() -> WorkOSClient:
    """Lazy WorkOSClient singleton.

    Tests monkeypatch this function (or the returned object) so no real network
    calls happen offline. Caching here means env-var reads happen once.
    """
    global _workos_client
    if _workos_client is None:
        api_key = os.environ.get("WORKOS_API_KEY")
        client_id = os.environ.get("WORKOS_CLIENT_ID")
        if not api_key or not client_id:
            raise RuntimeError(
                "WORKOS_API_KEY and WORKOS_CLIENT_ID must be set to use /auth/*"
            )
        _workos_client = WorkOSClient(api_key=api_key, client_id=client_id)
    return _workos_client


def _redirect_uri() -> str:
    """The /auth/callback URL WorkOS will bounce the browser back to.

    Mirrors the redirect URIs registered in the WorkOS dashboard. Defaults
    to localhost for dev; Railway sets WORKOS_REDIRECT_URI to the synzo.ai URL.
    """
    explicit = os.environ.get("WORKOS_REDIRECT_URI")
    if explicit:
        return explicit
    return url_for("auth.callback", _external=True)


def _safe_next(target: str | None) -> str:
    """Validate the `next` param so a hostile login link can't open-redirect.

    Accept only relative paths beginning with `/`, and reject `/auth/*` to
    prevent loops back into login. Anything else falls back to /dashboard.
    """
    if not target or not target.startswith("/"):
        return "/dashboard"
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return "/dashboard"
    if target.startswith("/auth/"):
        return "/dashboard"
    return target


# --- /auth/* ------------------------------------------------------------------


@bp.route("/auth/login")
def login():
    """Generate a fresh state token, store it in the session, redirect to AuthKit."""
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    session["post_login_next"] = _safe_next(request.args.get("next"))
    url = _workos().user_management.get_authorization_url(
        provider="authkit",
        redirect_uri=_redirect_uri(),
        state=state,
    )
    return redirect(url)


@bp.route("/auth/callback")
def callback():
    """Exchange the auth code for tokens, provision tenant rows, set session.

    Flow:
      1. Verify state param matches the value we stashed at /auth/login.
      2. authenticate_with_code → (user, tokens including access_token JWT).
      3. Upsert User row keyed on workos_user_id.
      4. If the user has no WorkOS org memberships yet: create one in WorkOS,
         mirror it into our orgs table, provision a free-tier quota, record
         an 'owner' membership locally, re-authenticate to obtain a JWT with
         the new org_id claim.
      5. Otherwise: pick the org from the access token's org_id claim, mirror
         the org + membership if we haven't yet, fall through.
      6. Set session: user_id, current_org_id. Redirect to next/dashboard.
      7. One-time log of `iss` claim until WORKOS_ISSUER is captured.
    """
    expected_state = session.pop("oauth_state", None)
    post_login_next = session.pop("post_login_next", "/dashboard")
    if not expected_state or request.args.get("state") != expected_state:
        return ("Invalid state parameter", 400)

    code = request.args.get("code")
    if not code:
        return ("Missing authorization code", 400)

    try:
        auth_response = _workos().user_management.authenticate_with_code(code=code)
    except Exception as e:
        logger.warning("WorkOS authenticate_with_code failed: %s", e)
        return ("Authentication failed", 401)

    workos_user = auth_response.user
    access_token = auth_response.access_token

    # Decode the access token without signature verification to read the org_id
    # claim — verifying would require WORKOS_ISSUER, which we capture on first
    # successful sign-in. The signed JWT path runs through auth._resolve_oauth.
    try:
        claims = jwt.decode(access_token, options={"verify_signature": False})
    except Exception as e:
        logger.warning("Could not decode WorkOS access token: %s", e)
        claims = {}

    # --- Upsert local User row ---
    user = (
        db.session.query(User)
        .filter_by(workos_user_id=workos_user.id)
        .one_or_none()
    )
    if user is None:
        user = User(workos_user_id=workos_user.id, email=workos_user.email)
        db.session.add(user)
        db.session.flush()
    else:
        user.email = workos_user.email  # may have changed in WorkOS
    user.last_seen_at = datetime.now(timezone.utc)

    # --- Resolve the user's current org ---
    workos_org_id = claims.get("org_id") or claims.get("organization_id")
    if not workos_org_id:
        # First-time signup: WorkOS hasn't put them in any org yet. Create one
        # and mirror it locally. Then re-authenticate so the next access token
        # carries the new org_id claim. We don't strictly need that token here
        # (we set the session ourselves), but it keeps Synzo + WorkOS in sync.
        org_name = (workos_user.email or "Workspace").split("@", 1)[0] + "'s Workspace"
        try:
            workos_org = _workos().organizations.create_organization(name=org_name)
            # WorkOS v8 takes a typed `role` (RoleSingle/RoleMultiple), not a
            # string. Omit it: WorkOS assigns the org's default role, and the
            # 'owner' role we care about is enforced via our own
            # org_memberships.role column further down (see the membership
            # upsert at end of this handler).
            _workos().organization_membership.create_organization_membership(
                user_id=workos_user.id,
                organization_id=workos_org.id,
            )
        except Exception as e:
            logger.error("WorkOS org/membership provisioning failed: %s", e)
            db.session.rollback()
            return ("Could not provision workspace", 500)
        workos_org_id = workos_org.id
        is_first_org_locally = True
    else:
        is_first_org_locally = False

    org = (
        db.session.query(Org)
        .filter_by(workos_org_id=workos_org_id)
        .one_or_none()
    )
    if org is None:
        org = Org(
            workos_org_id=workos_org_id,
            name=(workos_user.email or "Workspace").split("@", 1)[0] + "'s Workspace",
            plan="free",
        )
        db.session.add(org)
        db.session.flush()
        is_first_org_locally = True

    # Provision a free-tier quota row for the current period if missing.
    if is_first_org_locally:
        now = datetime.now(timezone.utc)
        period_start, period_end = _period_bounds(now)
        existing_quota = (
            db.session.query(Quota)
            .filter_by(org_id=org.id, period_start=period_start)
            .one_or_none()
        )
        if existing_quota is None:
            plan_limits = PLANS[org.plan]
            db.session.add(
                Quota(
                    org_id=org.id,
                    period_start=period_start,
                    period_end=period_end,
                    calls_remaining=plan_limits["calls_per_month"],
                    calls_limit=plan_limits["calls_per_month"],
                )
            )

    # Mirror membership. First membership in an org locally = owner.
    membership = (
        db.session.query(OrgMembership)
        .filter_by(user_id=user.id, org_id=org.id)
        .one_or_none()
    )
    if membership is None:
        any_membership_exists = (
            db.session.query(OrgMembership).filter_by(org_id=org.id).first()
            is not None
        )
        role = "member" if any_membership_exists else "owner"
        db.session.add(OrgMembership(user_id=user.id, org_id=org.id, role=role))

    db.session.commit()

    # --- Session ---
    session.permanent = True
    session["user_id"] = user.id
    session["current_org_id"] = org.id

    return redirect(post_login_next)


@bp.route("/auth/logout")
def logout():
    """Clear the local session. WorkOS sign-out happens at AuthKit."""
    session.clear()
    return redirect("/")


# --- /dashboard/* -------------------------------------------------------------


@bp.route("/dashboard")
@require_session
def dashboard():
    """Show plan, usage, API keys, members, and (if multi-org) the switcher."""
    principal = g.principal
    org = db.session.get(Org, principal.org_id)
    user = db.session.get(User, principal.user_id)

    now = datetime.now(timezone.utc)
    quota = (
        db.session.query(Quota)
        .filter(
            Quota.org_id == principal.org_id,
            Quota.period_start <= now,
            Quota.period_end > now,
        )
        .one_or_none()
    )

    api_keys = (
        db.session.query(ApiKey)
        .filter(ApiKey.org_id == principal.org_id, ApiKey.revoked_at.is_(None))
        .order_by(ApiKey.created_at.desc())
        .all()
    )

    memberships = (
        db.session.query(OrgMembership, User)
        .join(User, User.id == OrgMembership.user_id)
        .filter(OrgMembership.org_id == principal.org_id)
        .order_by(OrgMembership.created_at.asc())
        .all()
    )

    # Orgs this user can switch to. Always include the current one for display.
    user_orgs = (
        db.session.query(Org, OrgMembership.role)
        .join(OrgMembership, OrgMembership.org_id == Org.id)
        .filter(OrgMembership.user_id == principal.user_id)
        .order_by(Org.created_at.asc())
        .all()
    )

    return render_template(
        "dashboard.html",
        org=org,
        user=user,
        role=principal.role,
        plan=PLANS.get(org.plan, PLANS["free"]),
        quota=quota,
        api_keys=api_keys,
        memberships=memberships,
        user_orgs=user_orgs,
        newly_issued_key=session.pop("newly_issued_key", None),
    )


@bp.route("/dashboard/keys/issue", methods=["POST"])
@require_session
@require_role("admin")
def issue_key():
    """Issue an API key for the CURRENT org. Show raw key once via flash."""
    name = request.form.get("name") or None
    raw_key, _ = issue_api_key(org_id=g.principal.org_id, name=name)
    # Stash on session so the next render of /dashboard can display it ONCE.
    # We use the session (not flash) so a refresh doesn't keep showing it.
    session["newly_issued_key"] = raw_key
    return redirect(url_for("auth.dashboard"))


@bp.route("/dashboard/keys/<int:key_id>/revoke", methods=["POST"])
@require_session
@require_role("admin")
def revoke_key(key_id: int):
    """Revoke a key in the CURRENT org. The org_id filter is the tenant guard."""
    key = (
        db.session.query(ApiKey)
        .filter_by(id=key_id, org_id=g.principal.org_id)
        .one_or_none()
    )
    if key is None:
        abort(404)
    if key.revoked_at is None:
        key.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
    return redirect(url_for("auth.dashboard"))


@bp.route("/dashboard/members/invite", methods=["POST"])
@require_session
@require_role("admin")
def invite_member():
    """Invite a user (by email) to the current org via WorkOS.

    The invitee will get a WorkOS email; on accept, their /auth/callback will
    mirror the new membership into our DB.
    """
    email = (request.form.get("email") or "").strip()
    if not email or "@" not in email:
        flash("Enter a valid email address.", "error")
        return redirect(url_for("auth.dashboard"))

    org = db.session.get(Org, g.principal.org_id)
    if not org.workos_org_id:
        flash("This workspace is not linked to WorkOS yet.", "error")
        return redirect(url_for("auth.dashboard"))

    try:
        _workos().user_management.send_invitation(
            email=email,
            organization_id=org.workos_org_id,
        )
    except Exception as e:
        logger.warning("send_invitation failed for %s: %s", email, e)
        flash("Could not send invitation. Try again.", "error")
        return redirect(url_for("auth.dashboard"))

    flash(f"Invitation sent to {email}.", "success")
    return redirect(url_for("auth.dashboard"))


@bp.route("/dashboard/members/<int:membership_id>/role", methods=["POST"])
@require_session
@require_role("owner")
def update_member_role(membership_id: int):
    """Owner-only: change a member's role.

    Constraints (plan s6.5):
      - Can't promote to 'owner' here — owner transfer is a separate flow,
        out of scope for Phase 1.5.
      - Can't demote yourself (would leave the org without an owner unless
        we add transfer; for now refuse).
      - The org_id filter on the lookup is the tenant guard.
    """
    new_role = (request.form.get("role") or "").strip()
    if new_role not in {"admin", "member"}:
        # 'owner' is intentionally not allowed via this route.
        return ("Invalid role", 403)

    membership = (
        db.session.query(OrgMembership)
        .filter_by(id=membership_id, org_id=g.principal.org_id)
        .one_or_none()
    )
    if membership is None:
        abort(404)

    if membership.user_id == g.principal.user_id:
        return ("Cannot change your own role here", 403)

    membership.role = new_role
    db.session.commit()
    return redirect(url_for("auth.dashboard"))


@bp.route("/dashboard/switch-org/<int:org_id>")
@require_session
def switch_org(org_id: int):
    """Switch the active org to one this user is a member of, else 404."""
    membership = (
        db.session.query(OrgMembership)
        .filter_by(user_id=g.principal.user_id, org_id=org_id)
        .one_or_none()
    )
    if membership is None:
        abort(404)
    session["current_org_id"] = org_id
    return redirect(url_for("auth.dashboard"))


# --- Template context: current_user / current_org for the layout nav ---------


@bp.app_context_processor
def _inject_current_user():
    """Make `current_user`, `current_org`, and `current_role` available in
    every template — used by templates/layout.html to render the
    Sign in / Dashboard / Sign out nav buttons."""
    user_id = session.get("user_id")
    org_id = session.get("current_org_id")
    if not user_id or not org_id:
        return {"current_user": None, "current_org": None, "current_role": None}
    user = db.session.get(User, user_id)
    org = db.session.get(Org, org_id)
    role = None
    if user and org:
        membership = (
            db.session.query(OrgMembership)
            .filter_by(user_id=user_id, org_id=org_id)
            .one_or_none()
        )
        role = membership.role if membership else None
    return {"current_user": user, "current_org": org, "current_role": role}
