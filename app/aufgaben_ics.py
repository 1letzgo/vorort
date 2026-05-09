"""iCalendar-Export für Aufgaben (VTODO) — persönliche Abo-URLs wie bei Terminen."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from icalendar import Calendar, Todo
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.platform_models import Aufgabe, AufgabeZuweisung
from app.termin_kategorie import filter_aufgaben_fuer_ics

TZ = ZoneInfo("Europe/Berlin")


def build_ics_vtodo_calendar(
    aufgaben: list[Any],
    cal_name: str = "Aufgaben",
    *,
    ov_labels_for_mandant_slug: dict[str, str] | None = None,
) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//SPD Ortsverein//Wahlkampf Aufgaben//DE")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", cal_name)

    def _sort_key(a: Any) -> tuple:
        d = getattr(a, "due_at", None)
        return (0 if d is not None else 1, d or datetime.min, getattr(a, "id", 0))

    for a in sorted(aufgaben, key=_sort_key):
        td = Todo()
        td.add("uid", f"aufgabe-{a.id}@wahlkampf")
        summary = getattr(a, "title", "") or "Aufgabe"
        if ov_labels_for_mandant_slug:
            slug = str(getattr(a, "mandant_slug", "")).strip().lower()
            lab = ov_labels_for_mandant_slug.get(slug)
            if lab:
                summary = f"{lab}: {summary}"
        td.add("summary", summary)
        desc_parts: list[str] = []
        body = (getattr(a, "description", None) or "").strip()
        if body:
            desc_parts.append(body)
        zu = getattr(a, "zuweisungen", None) or []
        names: list[str] = []
        for z in zu:
            u = getattr(z, "user", None)
            if u is None:
                continue
            dn = (getattr(u, "display_name", None) or "").strip()
            un = (getattr(u, "username", None) or "").strip()
            names.append(dn or un or f"Nutzer #{getattr(u, 'id', '')}")
        if names:
            desc_parts.append("Zugewiesen: " + ", ".join(names))
        if desc_parts:
            td.add("description", "\n\n".join(desc_parts))
        due = getattr(a, "due_at", None)
        if due:
            if due.tzinfo is None:
                due = due.replace(tzinfo=TZ)
            td.add("due", due)
        if bool(getattr(a, "is_done", False)):
            td.add("status", "COMPLETED")
            td.add("percent-complete", 100)
        else:
            td.add("status", "NEEDS-ACTION")
            td.add("percent-complete", 0)
        td.add("dtstamp", datetime.now(TZ))
        cal.add_component(td)

    return cal.to_ical()


def all_aufgaben_multi_mandanten(
    db: Session,
    mandant_slugs: list[str],
    *,
    calendar_owner_user_id: int,
) -> list[Aufgabe]:
    if not mandant_slugs:
        return []
    slugs = sorted({s.strip().lower() for s in mandant_slugs if s and str(s).strip()})
    if not slugs:
        return []
    q = db.query(Aufgabe).options(
        selectinload(Aufgabe.zuweisungen).selectinload(AufgabeZuweisung.user),
    )
    raw = q.filter(func.lower(Aufgabe.mandant_slug).in_(slugs)).order_by(Aufgabe.id.asc()).all()
    return filter_aufgaben_fuer_ics(
        db, raw, calendar_owner_user_id=calendar_owner_user_id
    )
