# db/__init__.py
# Shared SQLAlchemy instance. Lives in its own module so blueprints and the
# auth decorator can import it without pulling in app.py (circular import).
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Importing models registers them on db.metadata so Alembic autogenerate sees them.
from db import models  # noqa: E402, F401
