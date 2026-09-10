"""Provision only the five explicitly requested Harvey evaluation identities.

Run from the repository root with .venv/Scripts/python.exe -m
scripts.provision_harvey_evaluation. Credentials and resumable state stay in
the operator's ACL-protected LOCALAPPDATA/Synzo/HarveyEvaluation directory.
Does not mark email addresses verified or accept invitations for recipients.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from workos import WorkOSClient
from workos._errors import BadRequestError
from workos.user_management._resource import PasswordPlaintext

from db.models import Org, OrgMembership, Quota, User

ROOT = Path(__file__).resolve().parents[1]
ORG_NAME = "Harvey Connector Evaluation"
EXTERNAL_ID = "synzo-harvey-connector-evaluation"
EMAILS = [f"connector_eval{i}@harvey.ai" for i in range(1, 6)]
BASE_URL = "https://www.synzo.ai"
STATE_PATH = Path(os.environ["LOCALAPPDATA"]) / "Synzo/HarveyEvaluation/state.json"


def emit(**fields):
    print(json.dumps(fields), flush=True)


def save(state):
    # The parent directory must already have a restrictive Windows ACL.
    if not STATE_PATH.parent.is_dir():
        raise RuntimeError("Create the restricted private credential directory first")
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(STATE_PATH)


def next_month(value):
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1)
    return value.replace(month=value.month + 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, choices=range(1, 6), default=5)
    parser.add_argument("--send-invitations", action="store_true")
    args = parser.parse_args()
    ca = ROOT / ".build_notes/harvey/windows-ca.pem"
    if not ca.exists():
        raise RuntimeError("Windows trust bundle has not been prepared")
    os.environ["SSL_CERT_FILE"] = str(ca)
    os.environ["REQUESTS_CA_BUNDLE"] = str(ca)
    cfg = dotenv_values(ROOT / ".env")
    client = WorkOSClient(api_key=cfg["WORKOS_API_KEY"], client_id=cfg["WORKOS_CLIENT_ID"])
    db_url = cfg["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    engine = create_engine(db_url, connect_args={"connect_timeout": 10})
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {
        "created_at": datetime.now(timezone.utc).isoformat(), "accounts": {},
    }
    if state.get("workos_org_id"):
        org = client.organizations.get_organization(state["workos_org_id"])
        if org.name != ORG_NAME:
            raise RuntimeError("Saved organization name does not match evaluation scope")
    else:
        matches = [o for o in client.organizations.list_organizations(search=ORG_NAME).data
                   if o.name == ORG_NAME and getattr(o, "external_id", None) == EXTERNAL_ID]
        if len(matches) > 1:
            raise RuntimeError("Multiple matching evaluation organizations")
        org = matches[0] if matches else client.organizations.create_organization(
            name=ORG_NAME, external_id=EXTERNAL_ID,
            metadata={"purpose": "harvey-connector-evaluation", "service": "Synzo"},
        )
        state["workos_org_id"] = org.id
        save(state)

    with Session(engine) as session:
        local_org = session.scalar(select(Org).where(Org.workos_org_id == org.id))
        if local_org is None:
            local_org = Org(workos_org_id=org.id, name=ORG_NAME, plan="starter")
            session.add(local_org)
            session.flush()
        if local_org.name != ORG_NAME:
            raise RuntimeError("Refusing to change a non-evaluation organization")
        local_org.plan = "starter"
        periods = state.get("quota_period_starts")
        if periods is None:
            start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            periods = []
            for _ in range(3):
                periods.append(start.isoformat())
                start = next_month(start)
            state["quota_period_starts"] = periods
            save(state)
        for value in periods:
            start = datetime.fromisoformat(value)
            quota = session.scalar(select(Quota).where(Quota.org_id == local_org.id,
                                                        Quota.period_start == start))
            if quota is None:
                session.add(Quota(org_id=local_org.id, period_start=start,
                                  period_end=next_month(start), calls_limit=10000,
                                  calls_remaining=10000))
        session.commit()
        state["synzo_org_id"] = local_org.id
        save(state)
    emit(organization=ORG_NAME, plan="starter", monthly_calls=10000,
         periods=state["quota_period_starts"])

    for index, email in enumerate(EMAILS[:args.limit], 1):
        entry = state["accounts"].setdefault(email, {})
        found = list(client.user_management.list_users(email=email).data)
        if len(found) > 1:
            raise RuntimeError("More than one WorkOS user for evaluation email")
        if not found:
            entry.setdefault("password", "Hv!9-" + secrets.token_urlsafe(30))
            save(state)
            user = client.user_management.create_user(
                email=email, first_name="Harvey", last_name=f"Connector Evaluation {index}",
                email_verified=False, password=PasswordPlaintext(password=entry["password"]),
                metadata={"purpose": "harvey-connector-evaluation"},
            )
        else:
            user = found[0]
            if entry.get("workos_user_id") and entry["workos_user_id"] != user.id:
                raise RuntimeError("Saved evaluation identity does not match WorkOS")
        entry["workos_user_id"] = user.id
        entry["email_verified"] = user.email_verified
        save(state)

        memberships = list(client.organization_membership.list_organization_memberships(
            organization_id=org.id, user_id=user.id).data)
        if not memberships:
            membership = client.organization_membership.create_organization_membership(
                user_id=user.id, organization_id=org.id)
        else:
            membership = memberships[0]
        entry["workos_membership_id"] = membership.id
        entry["workos_membership_status"] = str(getattr(membership, "status", "unknown"))
        save(state)
        with Session(engine) as session:
            local_user = session.scalar(select(User).where(User.workos_user_id == user.id))
            if local_user is None:
                local_user = User(workos_user_id=user.id, email=email)
                session.add(local_user)
                session.flush()
            local_membership = session.scalar(select(OrgMembership).where(
                OrgMembership.user_id == local_user.id,
                OrgMembership.org_id == state["synzo_org_id"]))
            if local_membership is None:
                session.add(OrgMembership(user_id=local_user.id,
                                         org_id=state["synzo_org_id"], role="member"))
            entry["synzo_user_id"] = local_user.id
            session.commit()
        save(state)
        emit(email=email, provisioned=True, membership=entry["workos_membership_status"],
             email_verified=user.email_verified)

        if entry.get("password") and not entry.get("authentication_checked_at"):
            response = requests.post("https://api.workos.com/user_management/authenticate", json={
                "grant_type": "password", "email": email, "password": entry["password"],
                "client_id": cfg["WORKOS_CLIENT_ID"], "client_secret": cfg["WORKOS_API_KEY"],
            }, timeout=30)
            payload = response.json()
            entry["authentication_http_status"] = response.status_code
            entry["authentication_checked_at"] = datetime.now(timezone.utc).isoformat()
            if response.ok and payload.get("access_token"):
                entry["access_token"] = payload["access_token"]
                entry["refresh_token"] = payload.get("refresh_token")
                entry["authentication_status"] = "authenticated"
            else:
                entry["authentication_status"] = payload.get("code") or payload.get("error") or "failed"
                if payload.get("pending_authentication_token"):
                    entry["pending_authentication_token"] = payload["pending_authentication_token"]
            save(state)
            emit(email=email, authentication=entry["authentication_status"],
                 http_status=response.status_code)

        if entry.get("access_token") and not entry.get("mcp_upload_verified"):
            result = requests.post(BASE_URL + "/mcp", headers={
                "Authorization": "Bearer " + entry["access_token"],
                "Accept": "application/json, text/event-stream",
            }, json={"jsonrpc": "2.0", "id": index, "method": "tools/call", "params": {
                "name": "upload_file", "arguments": {
                    "filename": f"harvey-evaluation-{index}.txt",
                    "content_base64": base64.b64encode(b"Synthetic Harvey connector evaluation file.").decode(),
                },
            }}, timeout=75)
            payload = result.json()
            success = bool(payload.get("result", {}).get("structuredContent", {}).get("content_url"))
            entry["mcp_upload_verified"] = success
            entry["mcp_upload_http_status"] = result.status_code
            if not success:
                entry["mcp_upload_error"] = payload.get("error", {}).get("code")
            save(state)
            emit(email=email, oauth_mcp_upload_verified=success, http_status=result.status_code,
                 error_code=entry.get("mcp_upload_error"))

        if args.send_invitations and not entry.get("invitation_id") and not entry.get("password_reset_id"):
            invitations = list(client.user_management.list_invitations(
                email=email, organization_id=org.id).data)
            active = [inv for inv in invitations
                      if str(getattr(getattr(inv, "state", ""), "value", getattr(inv, "state", ""))) == "pending"]
            try:
                invitation = active[0] if active else client.user_management.send_invitation(
                    email=email, organization_id=org.id, role_slug="member", expires_in_days=30)
                entry["invitation_id"] = invitation.id
                entry["invitation_state"] = str(getattr(invitation, "state", "unknown"))
                entry["invitation_expires_at"] = str(getattr(invitation, "expires_at", "unknown"))
                save(state)
                emit(email=email, invitation=entry["invitation_state"],
                     invitation_expires_at=entry["invitation_expires_at"])
            except BadRequestError as error:
                if error.code != "user_already_organization_member":
                    raise
                # These accounts have active memberships already, so WorkOS
                # rejects a redundant invitation. Its normal password-reset
                # flow lets the mailbox owner set their password and verify
                # their email. Never consume the returned token ourselves.
                reset = client.user_management.reset_password(email=email)
                entry["password_reset_id"] = reset.id
                entry["password_reset_expires_at"] = str(getattr(reset, "expires_at", "unknown"))
                entry["setup_email_requested_at"] = datetime.now(timezone.utc).isoformat()
                save(state)
                emit(email=email, password_setup_requested=True,
                     expires_at=entry["password_reset_expires_at"])
    emit(completed=True, private_state_path=str(STATE_PATH))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never print SDK response bodies, SQL connection URLs, or credentials.
        emit(error_type=type(error).__name__, status=getattr(error, "status_code", None),
             code=getattr(error, "code", None),
             message=getattr(error, "message", "Operation failed; inspect locally")[:300])
        raise SystemExit(1)
