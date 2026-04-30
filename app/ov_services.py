"""OV anlegen: Ordner, SQLite, Sharepic-Maske."""

from __future__ import annotations

import re
from pathlib import Path
from shutil import copy2

from sqlalchemy.orm import Session

from app import models
from app.config import mandant_dir, upload_dir_for_slug
from app.database import get_engine_for_mandant
from app.db_migrate import migrate_plakate_from_legacy_sqlite, run_sqlite_migrations
from app.platform_models import Ortsverband

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,79}$")


def validate_ov_slug(slug: str) -> str | None:
    s = slug.strip().lower()
    if not SLUG_RE.match(s):
        return (
            "Slug: 2–80 Zeichen, nur Kleinbuchstaben, Ziffern, Bindestrich, Unterstrich; "
            "muss mit Buchstabe oder Ziffer beginnen."
        )
    if s in {"admin", "static", "media", "login", "logout"}:
        return "Dieser Slug ist reserviert."
    return None


def ensure_sharepic_mask(slug: str) -> None:
    src = Path(__file__).resolve().parent / "static" / "sharepic-mask.png"
    dest_dir = upload_dir_for_slug(slug)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "sharepic-mask.png"
    if not dest.is_file() and src.is_file():
        copy2(src, dest)


def provision_ortsverband_storage(slug: str) -> None:
    """Legt Mandanten-DB und Upload-Struktur an (idempotent)."""
    slug = slug.strip().lower()
    mandant_dir(slug).mkdir(parents=True, exist_ok=True)
    ud = upload_dir_for_slug(slug)
    ud.mkdir(parents=True, exist_ok=True)
    (ud / "plakate").mkdir(parents=True, exist_ok=True)
    engine = get_engine_for_mandant(slug)
    models.Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    migrate_plakate_from_legacy_sqlite(engine)
    ensure_sharepic_mask(slug)


def register_ortsverband(db_platform: Session, slug: str, display_name: str) -> None:
    slug = slug.strip().lower()
    dn = " ".join(display_name.split()).strip() or slug
    db_platform.merge(Ortsverband(slug=slug, display_name=dn))
    db_platform.commit()
    provision_ortsverband_storage(slug)


def save_uploaded_sharepic_mask(slug: str, upload_file) -> None:
    """PNG aus Superadmin-Upload speichern."""
    from fastapi import UploadFile

    assert isinstance(upload_file, UploadFile)
    ud = upload_dir_for_slug(slug)
    ud.mkdir(parents=True, exist_ok=True)
    dest = ud / "sharepic-mask.png"
    if upload_file.content_type not in ("image/png", "application/octet-stream"):
        raise ValueError("Nur PNG erlaubt.")
    data = upload_file.file.read()
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("Datei zu groß (max. 8 MB).")
    dest.write_bytes(data)
