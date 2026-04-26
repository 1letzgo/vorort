from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event
from sqlalchemy.orm import Session

from app.models import Termin

TZ = ZoneInfo("Europe/Berlin")


def build_ics_calendar(termine: list[Termin], cal_name: str = "SPD Wahlkampf") -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//SPD Ortsverein//Wahlkampf//DE")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", cal_name)

    for t in sorted(termine, key=lambda x: x.starts_at):
        ev = Event()
        ev.add("uid", f"termin-{t.id}@wahlkampf")
        ev.add("summary", t.title)
        if t.description:
            ev.add("description", t.description)
        if t.location:
            ev.add("location", t.location)
        start = t.starts_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=TZ)
        end = t.ends_at
        if end:
            if end.tzinfo is None:
                end = end.replace(tzinfo=TZ)
        else:
            end = start + timedelta(hours=1)
        ev.add("dtstart", start)
        ev.add("dtend", end)
        ev.add("dtstamp", datetime.now(TZ))
        cal.add_component(ev)

    return cal.to_ical()


def all_termine_for_feed(db: Session) -> list[Termin]:
    return db.query(Termin).order_by(Termin.starts_at.asc()).all()
