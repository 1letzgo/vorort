#!/usr/bin/env python3
"""Legt einen Benutzer an (z. B. Recovery). Normalerweise reicht die Registrierung:
Der erste registrierte Nutzer wird automatisch Admin und freigeschaltet.

    python scripts/create_user.py --username max --password geheim --display "Max M." [--admin]

Setzt DATABASE_URL wie die App (Standard: ./wahlkampf.db im Projektroot).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Projektroot auf path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / 'wahlkampf.db'}")

from app.auth import hash_password  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.db_migrate import run_sqlite_migrations  # noqa: E402
from app import models  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Benutzer für Wahlkampf-App anlegen")
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--display", default="", help="Anzeigename (optional)")
    p.add_argument(
        "--admin",
        action="store_true",
        help="Als Administrator (darf alle Termine bearbeiten/löschen)",
    )
    args = p.parse_args()

    models.Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    db = SessionLocal()
    try:
        u = args.username.strip()
        if db.query(models.User).filter(models.User.username == u).first():
            print(f"Benutzer „{u}“ existiert bereits.", file=sys.stderr)
            sys.exit(1)
        was_empty = db.query(models.User).count() == 0
        user = models.User(
            username=u,
            password_hash=hash_password(args.password),
            display_name=(args.display or "").strip(),
            is_admin=args.admin,
            is_approved=True,
        )
        db.add(user)
        db.commit()
        if was_empty:
            db.merge(models.AppSetting(key="founder_done", value="1"))
            db.commit()
        role = "Admin" if args.admin else "Benutzer"
        print(f"Benutzer „{u}“ angelegt (id={user.id}, {role}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
