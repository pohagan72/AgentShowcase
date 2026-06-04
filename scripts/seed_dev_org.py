"""Seed a dev org + quota + API key against whatever DATABASE_URL points at.

Idempotent: if a `dev` org already exists, reuse it and just issue a new key.
Prints the raw sk_synzo_... key to stdout exactly once — the DB only stores the
sha256 hash, so this is your only chance to capture it.

Usage (from repo root):
    .venv/Scripts/python.exe -m scripts.seed_dev_org

Reads DATABASE_URL from .env. With the plan's setup, that's the Railway public
proxy when run locally and the internal hostname when run on Railway itself.

After running, set the printed key in your shell:
    export SYNZO_DEV_KEY=sk_synzo_xxxxx        # bash
    $env:SYNZO_DEV_KEY = "sk_synzo_xxxxx"      # PowerShell
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

# Initialize the Flask app context so SQLAlchemy + Config load the same way as
# in production. Importing create_app pulls in Presidio/spaCy which takes ~80s
# cold — acceptable for a one-off seed script.
from app import create_app
from auth import PLANS, issue_api_key, _period_bounds
from db import db
from db.models import Org, Quota

DEV_ORG_NAME = "dev"
DEV_PLAN = "free"


def main() -> int:
    app = create_app()
    with app.app_context():
        org = db.session.query(Org).filter_by(name=DEV_ORG_NAME).one_or_none()
        if org is None:
            org = Org(name=DEV_ORG_NAME, plan=DEV_PLAN)
            db.session.add(org)
            db.session.commit()
            print(f"[seed] created org id={org.id} name={DEV_ORG_NAME} plan={DEV_PLAN}")
        else:
            print(f"[seed] reusing existing org id={org.id} name={DEV_ORG_NAME} plan={org.plan}")

        # Ensure a quota row exists for the current period.
        now = datetime.now(timezone.utc)
        period_start, period_end = _period_bounds(now)
        quota = (
            db.session.query(Quota)
            .filter_by(org_id=org.id, period_start=period_start)
            .one_or_none()
        )
        if quota is None:
            plan_limits = PLANS[org.plan]
            quota = Quota(
                org_id=org.id,
                period_start=period_start,
                period_end=period_end,
                calls_remaining=plan_limits["calls_per_month"],
                calls_limit=plan_limits["calls_per_month"],
            )
            db.session.add(quota)
            db.session.commit()
            print(
                f"[seed] created quota id={quota.id} "
                f"period={period_start.date()}..{period_end.date()} "
                f"calls={quota.calls_remaining}/{quota.calls_limit}"
            )
        else:
            print(
                f"[seed] reusing quota id={quota.id} "
                f"calls_remaining={quota.calls_remaining}/{quota.calls_limit}"
            )

        raw_key, record = issue_api_key(org_id=org.id, name="dev-seed")
        print(f"[seed] issued api_key id={record.id} prefix={record.prefix}")
        print()
        print("=" * 60)
        print("RAW API KEY (shown once, not stored — save it now):")
        print(raw_key)
        print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
