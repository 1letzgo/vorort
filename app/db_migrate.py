"""Leichte Schema-Anpassungen für SQLite (ohne Alembic)."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def run_sqlite_migrations(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("users"):
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as conn:
        if "is_admin" not in cols:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"),
            )
        if "is_approved" not in cols:
            # Bestehende Konten gelten als freigegeben (vor Registrierungs-Flow)
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN is_approved INTEGER NOT NULL DEFAULT 1"
                ),
            )
