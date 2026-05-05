"""ICS/Webcal-Abo → Fraktionstermine (dedupliziert über cal_import_key)."""

from __future__ import annotations

import hashlib
import logging
import urllib.request
from datetime import date, datetime, time, timezone
from typing import Any
from urllib.parse import urlparse

from icalendar import Calendar
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import CAL_FETCH_TIMEOUT_SECONDS
from app.mandant_features import FEATURE_FRAKTION, is_mandant_feature_enabled
from app.platform_models import Ortsverband, Termin

logger = logging.getLogger(__name__)


def validate_and_normalize_cal_subscription_url(raw: str) -> tuple[str | None, str | None]:
    """Speicherformat: https/http (webcal:// wird normalisiert). Leer → Abo ohne URL."""
    s = (raw or "").strip()
    if not s:
        return None, None
    if len(s) > 8000:
        return None, "Die Kalender-URL ist zu lang."
    if s.lower().startswith("webcal://"):
        s = "https://" + s[len("webcal://") :]
    p = urlparse(s)
    if p.scheme not in ("http", "https") or not p.netloc:
        return None, "Bitte eine http(s)- oder webcal://-Kalenderadresse angeben."
    return s, None


def normalize_calendar_fetch_url(raw: str) -> str:
    """webcal:// → https:// für HTTP-Abruf."""
    s = (raw or "").strip()
    if s.lower().startswith("webcal://"):
        return "https://" + s[len("webcal://") :]
    return s


def fetch_ics_bytes(cal_url: str, *, timeout: int | None = None) -> bytes:
    timeout = CAL_FETCH_TIMEOUT_SECONDS if timeout is None else timeout
    fetch_u = normalize_calendar_fetch_url(cal_url.strip())
    parsed = urlparse(fetch_u)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Ungültige Kalender-URL.")
    req = urllib.request.Request(
        fetch_u,
        headers={
            "User-Agent": "Wahlkampf-Fraktion-Cal/1.0",
            "Accept": "text/calendar, application/calendar+json, */*",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _aware_to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _dtstart_to_datetime(val: Any) -> datetime | None:
    if isinstance(val, datetime):
        return _aware_to_naive_utc(val)
    if isinstance(val, date):
        return datetime.combine(val, time.min)
    return None


def _prop_as_str(component, name: str, max_len: int) -> str:
    raw = component.get(name)
    if raw is None:
        return ""
    s = str(raw).strip()
    return s[:max_len] if len(s) > max_len else s


def _event_import_key(uid: str, starts_at: datetime, recurrence_id: Any) -> str:
    rid = ""
    if recurrence_id is not None:
        try:
            dt = recurrence_id.dt
            rid = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
        except Exception:
            rid = str(recurrence_id)
    base = f"{uid}\n{starts_at.isoformat()}\n{rid}".encode("utf-8", errors="replace")
    return hashlib.sha256(base).hexdigest()


def parse_vevents_from_ics(raw: bytes) -> list[dict]:
    cal = Calendar.from_ical(raw)
    out: list[dict] = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        if component.get("rrule"):
            logger.debug("Kalender: VEVENT mit RRULE übersprungen (nicht expandiert).")
            continue
        dtstart_prop = component.get("dtstart")
        if dtstart_prop is None:
            continue
        dt_raw = dtstart_prop.dt
        starts_at = _dtstart_to_datetime(dt_raw)
        if starts_at is None:
            continue

        uid = _prop_as_str(component, "uid", 500)
        if not uid:
            uid = f"noid-{starts_at.isoformat()}"

        ends_at: datetime | None = None
        dtend_prop = component.get("dtend")
        if dtend_prop is not None:
            ends_at = _dtstart_to_datetime(dtend_prop.dt)

        title = _prop_as_str(component, "summary", 200) or "(Kalender)"
        location = _prop_as_str(component, "location", 300)
        description = _prop_as_str(component, "description", 20000)

        out.append(
            {
                "title": title,
                "location": location,
                "description": description,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "import_key": _event_import_key(
                    uid,
                    starts_at,
                    component.get("recurrence-id"),
                ),
            }
        )
    return out


def import_fraktion_termine_from_calendar(
    db: Session,
    mandant_slug: str,
    cal_url: str,
) -> tuple[int, str | None]:
    """Legt fehlende Fraktionstermine aus ICS/Webcal an."""
    ms = mandant_slug.strip().lower()
    if not is_mandant_feature_enabled(db, ms, FEATURE_FRAKTION):
        return 0, "Fraktion ist für diesen Ortsverband nicht aktiviert."

    url = cal_url.strip()
    if not url:
        return 0, "Keine Kalender-URL konfiguriert."

    try:
        raw = fetch_ics_bytes(url)
    except Exception as e:
        logger.warning("Kalender fetch failed mandant=%s: %s", ms, e)
        return 0, f"Kalender konnte nicht geladen werden: {e}"

    try:
        events = parse_vevents_from_ics(raw)
    except Exception as e:
        logger.warning("Kalender parse failed mandant=%s: %s", ms, e)
        return 0, f"Kalender konnte nicht gelesen werden: {e}"

    created = 0
    for ev in events:
        dedupe = ev["import_key"]
        exists = (
            db.query(Termin.id)
            .filter(Termin.mandant_slug == ms, Termin.cal_import_key == dedupe)
            .first()
        )
        if exists:
            continue

        title = ev["title"].strip() or "(Kalender)"
        desc = (ev["description"] or "").strip()
        loc = (ev["location"] or "").strip()

        termin = Termin(
            mandant_slug=ms,
            title=title[:200],
            description=desc[:20000] if len(desc) > 20000 else desc,
            location=loc[:300],
            starts_at=ev["starts_at"],
            ends_at=ev["ends_at"],
            created_by_id=None,
            is_fraktion_termin=True,
            fraktion_vertraulich=False,
            cal_import_key=dedupe,
        )
        db.add(termin)
        try:
            db.commit()
            created += 1
        except IntegrityError:
            db.rollback()

    return created, None


def run_all_fraktion_cal_subscriptions() -> None:
    """Alle aktiven Abos (URL + Abo an + FEATURE_FRAKTION)."""
    from sqlalchemy.orm import sessionmaker

    from app.platform_database import platform_engine

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=platform_engine())
    db = SessionLocal()
    try:
        ovs = (
            db.query(Ortsverband)
            .filter(
                Ortsverband.fraktion_cal_feed_url.isnot(None),
                Ortsverband.fraktion_cal_feed_url != "",
                Ortsverband.fraktion_cal_abo_active.is_(True),
            )
            .all()
        )
        for ov in ovs:
            url = (ov.fraktion_cal_feed_url or "").strip()
            if not url:
                continue
            if not is_mandant_feature_enabled(db, ov.slug, FEATURE_FRAKTION):
                continue
            n, err = import_fraktion_termine_from_calendar(db, ov.slug, url)
            if err:
                logger.info(
                    "Kalender mandant=%s created=%s msg=%s",
                    ov.slug,
                    n,
                    err,
                )
            elif n:
                logger.info("Kalender mandant=%s created=%s", ov.slug, n)
    finally:
        db.close()
