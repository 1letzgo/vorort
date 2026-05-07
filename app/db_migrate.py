"""SQLite-Hilfen ohne Alembic: Legacy-Dateilayout + Schema-Anpassungen nur für platform.db."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError

from app.config import BASE_DIR, mandant_dir, sqlite_database_path, upload_dir_for_slug


def migrate_termine_created_by_nullable_sqlite(engine: Engine) -> None:
    """Macht termine.created_by_id optional + ON DELETE SET NULL (SQLite-Tabellenumbau).

    Ohne das schlägt das Löschen eines Nutzers mit FK-Prüfung fehl, sobald noch Termine
    auf platform_users verweisen (ORM hatte NOT NULL ohne ON DELETE).
    """
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("termine"):
        return
    with engine.connect() as conn:
        pragma_rows = conn.execute(text("PRAGMA table_info(termine)")).fetchall()
    cb_row = next((r for r in pragma_rows if r[1] == "created_by_id"), None)
    if cb_row is None:
        return
    # PRAGMA table_info: Spalte 3 = notnull (1 = NOT NULL)
    if cb_row[3] == 0:
        return

    ddl_new = """
            CREATE TABLE termine__wk_rebuild (
              id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
              mandant_slug VARCHAR(80) NOT NULL,
              title VARCHAR(200) NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              location VARCHAR(300) NOT NULL DEFAULT '',
              starts_at DATETIME NOT NULL,
              ends_at DATETIME,
              image_path VARCHAR(500),
              externe_teilnehmer_json TEXT NOT NULL DEFAULT '[]',
              created_by_id INTEGER,
              created_at DATETIME NOT NULL,
              FOREIGN KEY(mandant_slug) REFERENCES ortsverbaende(slug) ON DELETE CASCADE,
              FOREIGN KEY(created_by_id) REFERENCES platform_users(id) ON DELETE SET NULL
            )
            """
    copy_sql = """
            INSERT INTO termine__wk_rebuild (
              id, mandant_slug, title, description,
              location, starts_at, ends_at, image_path, externe_teilnehmer_json,
              created_by_id, created_at
            )
            SELECT
              id, mandant_slug, title, description,
              location, starts_at, ends_at, image_path, externe_teilnehmer_json,
              created_by_id, created_at
            FROM termine
            """

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text(ddl_new))
        conn.execute(text(copy_sql))
        conn.execute(text("DROP TABLE termine"))
        conn.execute(text("ALTER TABLE termine__wk_rebuild RENAME TO termine"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_termine_mandant_slug "
                "ON termine (mandant_slug)"
            ),
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_termine_starts_at ON termine (starts_at)"
            ),
        )
        conn.execute(text("PRAGMA foreign_keys=ON"))


def migrate_termin_teilnahme_status_sqlite(engine: Engine) -> None:
    """Spalte teilnahme_status: zugesagt vs. abgesagt (bestehende Zeilen = Zusage)."""
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("termin_teilnahmen"):
        return
    cols = {c["name"] for c in insp.get_columns("termin_teilnahmen")}
    if "teilnahme_status" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE termin_teilnahmen ADD COLUMN teilnahme_status "
                "VARCHAR(16) NOT NULL DEFAULT 'zugesagt'"
            ),
        )


def migrate_legacy_flat_into_mandant(slug: str) -> None:
    """Kopiert alt `./wahlkampf.db` und `./uploads` nach `mandanten/<slug>/`, falls Ziel noch leer."""
    slug = slug.strip().lower()
    mandant_dir(slug).mkdir(parents=True, exist_ok=True)
    target_db = sqlite_database_path(slug)
    if not target_db.is_file():
        candidates = [BASE_DIR / "wahlkampf.db", Path("/data/wahlkampf.db")]
        raw = os.environ.get("DATABASE_URL", "").strip()
        if raw.startswith("sqlite"):
            try:
                u = make_url(raw)
                if u.database and u.database != ":memory:":
                    lp = Path(u.database)
                    if not lp.is_absolute():
                        lp = (BASE_DIR / lp).resolve()
                    else:
                        lp = lp.resolve()
                    if lp.is_file():
                        candidates.insert(0, lp)
            except Exception:
                pass
        for src in candidates:
            if src.is_file():
                shutil.copy2(src, target_db)
                break

    dest_u = upload_dir_for_slug(slug)
    if not dest_u.exists() or not any(dest_u.iterdir()):
        for legacy_u in (BASE_DIR / "uploads", Path("/data/uploads")):
            if legacy_u.is_dir() and any(legacy_u.iterdir()):
                dest_u.mkdir(parents=True, exist_ok=True)
                for item in legacy_u.iterdir():
                    target_item = dest_u / item.name
                    if item.is_dir():
                        shutil.copytree(item, target_item, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, target_item)
                break


def run_platform_sqlite_migrations(engine: Engine) -> None:
    """Bestehende platform.db an aktuelles PlatformBase-ORM anbinden (fehlende Spalten).

    `metadata.create_all` legt keine neuen Spalten an bestehenden Tabellen an.
    """
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if insp.has_table("platform_users"):
        cols = {c["name"] for c in insp.get_columns("platform_users")}
        with engine.begin() as conn:
            if "display_name" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE platform_users ADD COLUMN display_name "
                        "VARCHAR(120) NOT NULL DEFAULT ''"
                    ),
                )
            if "calendar_token" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE platform_users ADD COLUMN calendar_token VARCHAR(64)"
                    ),
                )
            if "menu_ov_card_open_json" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE platform_users ADD COLUMN menu_ov_card_open_json "
                        "TEXT NOT NULL DEFAULT '{}'"
                    ),
                )
    migrate_termine_created_by_nullable_sqlite(engine)
    migrate_termin_teilnahme_status_sqlite(engine)
    migrate_termine_promoted_all_ovs_sqlite(engine)
    migrate_termine_attachments_json_sqlite(engine)
    migrate_termine_drop_vorbereitung_nachbereitung_sqlite(engine)
    migrate_ov_memberships_fraktion_member_sqlite(engine)
    migrate_termine_fraktion_flags_sqlite(engine)
    migrate_ortsverbaende_fraktion_calendar_subscription_sqlite(engine)
    migrate_termine_cal_import_key_sqlite(engine)
    migrate_termine_link_url_sqlite(engine)
    migrate_ov_memberships_vorstand_member_sqlite(engine)
    migrate_termine_kategorie_sqlite(engine)
    migrate_extern_cal_subscriptions_sqlite(engine)


def migrate_extern_cal_subscriptions_sqlite(engine: Engine) -> None:
    """Eigene Tabelle für Kalender-Abos (mehrere pro OV); übernimmt Legacy aus ortsverbaende.*."""
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("ortsverbaende"):
        return
    with engine.begin() as conn:
        if not insp.has_table("extern_cal_subscriptions"):
            conn.execute(
                text(
                    """
                    CREATE TABLE extern_cal_subscriptions (
                      id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                      mandant_slug VARCHAR(80) NOT NULL,
                      label VARCHAR(200) NOT NULL DEFAULT '',
                      feed_url TEXT,
                      abo_active BOOLEAN NOT NULL DEFAULT 0,
                      created_at DATETIME NOT NULL,
                      FOREIGN KEY(mandant_slug) REFERENCES ortsverbaende (slug) ON DELETE CASCADE
                    )
                    """
                ),
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_extern_cal_sub_mandant "
                    "ON extern_cal_subscriptions (mandant_slug)"
                ),
            )
        conn.execute(
            text(
                """
                INSERT INTO extern_cal_subscriptions (mandant_slug, label, feed_url, abo_active, created_at)
                SELECT slug, '', TRIM(fraktion_cal_feed_url),
                       CASE WHEN fraktion_cal_abo_active THEN 1 ELSE 0 END,
                       datetime('now')
                FROM ortsverbaende
                WHERE fraktion_cal_feed_url IS NOT NULL
                  AND LENGTH(TRIM(fraktion_cal_feed_url)) > 0
                  AND NOT EXISTS (
                    SELECT 1 FROM extern_cal_subscriptions e
                    WHERE e.mandant_slug = ortsverbaende.slug
                      AND IFNULL(TRIM(e.feed_url), '') = TRIM(ortsverbaende.fraktion_cal_feed_url)
                  )
                """
            ),
        )
        conn.execute(
            text(
                """
                UPDATE ortsverbaende
                SET fraktion_cal_feed_url = NULL, fraktion_cal_abo_active = 0
                WHERE fraktion_cal_feed_url IS NOT NULL
                  AND LENGTH(TRIM(fraktion_cal_feed_url)) > 0
                """
            ),
        )


def migrate_ov_memberships_fraktion_member_sqlite(engine: Engine) -> None:
    """Fraktionsmitgliedschaft pro OV (Teilmenge der Verbandsmitglieder)."""
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("ov_memberships"):
        return
    cols = {c["name"] for c in insp.get_columns("ov_memberships")}
    if "fraktion_member" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE ov_memberships ADD COLUMN fraktion_member "
                "BOOLEAN NOT NULL DEFAULT 0"
            ),
        )


def migrate_ortsverbaende_fraktion_calendar_subscription_sqlite(engine: Engine) -> None:
    """ICS/Webcal-URL + Abo-Schalter; übernimmt Legacy-Spalte fraktion_rss_feed_url falls vorhanden."""
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("ortsverbaende"):
        return
    cols = {c["name"] for c in insp.get_columns("ortsverbaende")}
    with engine.begin() as conn:
        if "fraktion_cal_feed_url" not in cols:
            conn.execute(text("ALTER TABLE ortsverbaende ADD COLUMN fraktion_cal_feed_url TEXT"))
        if "fraktion_cal_abo_active" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE ortsverbaende ADD COLUMN fraktion_cal_abo_active "
                    "BOOLEAN NOT NULL DEFAULT 0"
                ),
            )
        if "fraktion_rss_feed_url" in cols:
            conn.execute(
                text(
                    """
                    UPDATE ortsverbaende SET fraktion_cal_feed_url =
                        REPLACE(REPLACE(TRIM(fraktion_rss_feed_url), 'webcal://', 'https://'), 'WEBCAL://', 'https://')
                    WHERE (fraktion_cal_feed_url IS NULL OR TRIM(fraktion_cal_feed_url) = '')
                      AND fraktion_rss_feed_url IS NOT NULL AND LENGTH(TRIM(fraktion_rss_feed_url)) > 0
                    """
                ),
            )
            try:
                conn.execute(text("ALTER TABLE ortsverbaende DROP COLUMN fraktion_rss_feed_url"))
            except OperationalError:
                pass


def migrate_termine_cal_import_key_sqlite(engine: Engine) -> None:
    """Dedupe-Spalte für Kalenderimport (früher rss_import_key)."""
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("termine"):
        return
    cols = {c["name"] for c in insp.get_columns("termine")}
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS uq_termine_mandant_rss_import"))
        if "cal_import_key" not in cols and "rss_import_key" in cols:
            conn.execute(
                text("ALTER TABLE termine RENAME COLUMN rss_import_key TO cal_import_key"),
            )
        elif "cal_import_key" not in cols:
            conn.execute(text("ALTER TABLE termine ADD COLUMN cal_import_key VARCHAR(128)"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_termine_mandant_cal_import "
                "ON termine (mandant_slug, cal_import_key)"
            ),
        )


def migrate_termine_link_url_sqlite(engine: Engine) -> None:
    """Optionaler Detail-Link je Termin (Web/RIS/…)."""
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("termine"):
        return
    cols = {c["name"] for c in insp.get_columns("termine")}
    if "link_url" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE termine ADD COLUMN link_url VARCHAR(2000)"))


def migrate_termine_fraktion_flags_sqlite(engine: Engine) -> None:
    """Fraktionstermine + optional vertraulich (nur Fraktionsmitglieder)."""
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("termine"):
        return
    cols = {c["name"] for c in insp.get_columns("termine")}
    with engine.begin() as conn:
        if "is_fraktion_termin" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE termine ADD COLUMN is_fraktion_termin "
                    "BOOLEAN NOT NULL DEFAULT 0"
                ),
            )
        if "fraktion_vertraulich" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE termine ADD COLUMN fraktion_vertraulich "
                    "BOOLEAN NOT NULL DEFAULT 0"
                ),
            )


def migrate_ov_memberships_vorstand_member_sqlite(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("ov_memberships"):
        return
    cols = {c["name"] for c in insp.get_columns("ov_memberships")}
    if "vorstand_member" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE ov_memberships ADD COLUMN vorstand_member "
                "BOOLEAN NOT NULL DEFAULT 0"
            ),
        )


def migrate_termine_kategorie_sqlite(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("termine"):
        return
    cols = {c["name"] for c in insp.get_columns("termine")}
    with engine.begin() as conn:
        if "termin_kategorie" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE termine ADD COLUMN termin_kategorie "
                    "VARCHAR(32) NOT NULL DEFAULT 'verband'"
                ),
            )
        conn.execute(
            text(
                "UPDATE termine SET termin_kategorie = 'fraktion' "
                "WHERE is_fraktion_termin = 1 AND fraktion_vertraulich = 1 "
                "AND (termin_kategorie IS NULL OR termin_kategorie = '' "
                "OR termin_kategorie = 'verband')"
            ),
        )
        conn.execute(
            text(
                "UPDATE termine SET termin_kategorie = 'verband' "
                "WHERE is_fraktion_termin = 1 AND (fraktion_vertraulich = 0 "
                "OR fraktion_vertraulich IS NULL) "
                "AND (termin_kategorie IS NULL OR termin_kategorie = '' "
                "OR termin_kategorie = 'verband')"
            ),
        )


def migrate_termine_drop_vorbereitung_nachbereitung_sqlite(engine: Engine) -> None:
    """Entfernt Spalten vorbereitung/nachbereitung (Kommentare übernehmen den Zweck). SQLite ≥3.35."""
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("termine"):
        return
    cols = {c["name"] for c in insp.get_columns("termine")}
    for name in ("vorbereitung", "nachbereitung"):
        if name not in cols:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE termine DROP COLUMN "{name}"'))
        except OperationalError:
            break


def migrate_termine_attachments_json_sqlite(engine: Engine) -> None:
    """JSON-Liste von Dateianhängen (Pfad unter uploads + Anzeigename)."""
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("termine"):
        return
    cols = {c["name"] for c in insp.get_columns("termine")}
    if "attachments_json" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE termine ADD COLUMN attachments_json "
                "TEXT NOT NULL DEFAULT '[]'"
            ),
        )


def migrate_termine_promoted_all_ovs_sqlite(engine: Engine) -> None:
    """Boolean promoted_all_ovs: Kreis-Termine optional in allen OVs listen."""
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("termine"):
        return
    cols = {c["name"] for c in insp.get_columns("termine")}
    if "promoted_all_ovs" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE termine ADD COLUMN promoted_all_ovs "
                "BOOLEAN NOT NULL DEFAULT 0"
            ),
        )
