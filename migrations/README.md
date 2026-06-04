# Database migrations

Alembic is wired against the Flask app's `SQLALCHEMY_DATABASE_URI` (read from
`DATABASE_URL`). Run all commands from the repo root.

## Common commands

```bash
# Apply all pending migrations to the database DATABASE_URL points at
alembic upgrade head

# Roll back the most recent migration
alembic downgrade -1

# Show current revision
alembic current

# Generate a new migration from model diffs (review the output before committing)
alembic revision --autogenerate -m "describe the change"
```

## Notes

- `migrations/env.py` builds the Flask app to read `DATABASE_URL` — same code
  path on laptop and Railway.
- Locally `DATABASE_URL` points at Railway's public proxy; on Railway it
  resolves the internal Postgres hostname. Either works.
- Never edit a migration after it's been applied anywhere. Write a new one.
