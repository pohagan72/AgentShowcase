# migrations/env.py
# Alembic environment. Reads DATABASE_URL directly from .env (via python-dotenv)
# and imports only the model module — never the Flask app — so migrations can
# run in lightweight environments (CI, fresh checkouts) without the full
# Gemini/Presidio dependency stack installed.
from __future__ import annotations

import logging
import os
import sys
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# Make the project root importable when `alembic` runs from the repo root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()

from db import db  # noqa: E402  (imports db/models.py for side effects)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "DATABASE_URL is not set. Alembic needs it to connect. "
        "Set it in .env (local) or Railway service variables (deployed)."
    )
# psycopg3 (drop-in replacement for psycopg2) is what we install. SQLAlchemy
# defaults postgresql:// to psycopg2; explicitly select the psycopg driver.
if database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
elif database_url.startswith("postgres://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = db.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
