from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, time
from pathlib import Path
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware

from app import models
from app.auth import hash_password, verify_password
from app.config import (
    ICS_TOKEN,
    MAX_UPLOAD_MB,
    SECRET_KEY,
    SESSION_COOKIE,
    UPLOAD_DIR,
)
from app.database import engine, get_db
from app.db_migrate import run_sqlite_migrations
from app.deps import AdminUser, CurrentUser
from app.ics_service import all_termine_for_feed, build_ics_calendar
from app.settings_store import ensure_ics_token_for_ui, verify_ics_token

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp"}
EXT_MAP = {".jpg": ".jpg", ".jpeg": ".jpg", ".png": ".png", ".webp": ".webp"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Wahlkampf", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie=SESSION_COOKIE)


@app.exception_handler(HTTPException)
async def http_exc(request: Request, exc: HTTPException):
    accept = request.headers.get("accept") or ""
    wants_html = "text/html" in accept or accept.startswith("*/*")
    if exc.status_code == 401 and wants_html:
        if exc.detail == "Konto noch nicht freigegeben.":
            return RedirectResponse("/login?pending=1", status_code=302)
        return RedirectResponse("/login", status_code=302)
    if exc.status_code == 403 and wants_html:
        msg = exc.detail if isinstance(exc.detail, str) else "Keine Berechtigung."
        return templates.TemplateResponse(
            request,
            "forbidden.html",
            {"message": msg},
            status_code=403,
        )
    return await http_exception_handler(request, exc)


app.mount("/media", StaticFiles(directory=str(UPLOAD_DIR)), name="media")


def _can_manage_termin(user: models.User, termin: models.Termin) -> bool:
    return bool(user.is_admin or termin.created_by_id == user.id)


def _unlink_upload(rel: Optional[str]) -> None:
    if not rel:
        return
    p = UPLOAD_DIR / rel
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


def _safe_ext(filename: Optional[str], content_type: Optional[str]) -> str:
    if filename:
        suf = Path(filename).suffix.lower()
        if suf in EXT_MAP:
            return EXT_MAP[suf]
    if content_type == "image/jpeg":
        return ".jpg"
    if content_type == "image/png":
        return ".png"
    if content_type == "image/webp":
        return ".webp"
    return ""


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/termine", status_code=302)
    return templates.TemplateResponse(request, "home.html", {})


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    info = None
    if request.query_params.get("pending") == "1":
        info = "Dein Konto ist noch nicht freigegeben. Bitte warte auf einen Administrator."
    if request.query_params.get("registered") == "1":
        info = (
            "Registrierung gespeichert. Sobald ein Administrator dich freischaltet, "
            "kannst du dich anmelden."
        )
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": None, "info": info},
    )


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    user = db.query(models.User).filter(models.User.username == username.strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Benutzername oder Passwort falsch.", "info": None},
            status_code=401,
        )
    if not user.is_approved:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": None,
                "info": "Dein Konto ist noch nicht freigegeben. Bitte warte auf einen Administrator.",
            },
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/termine", status_code=302)


@app.get("/registrierung", response_class=HTMLResponse)
def registrierung_form(request: Request):
    return templates.TemplateResponse(
        request,
        "registrierung.html",
        {"error": None},
    )


@app.post("/registrierung", response_class=HTMLResponse)
def registrierung_submit(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    password2: Annotated[str, Form()],
):
    username = " ".join(name.split()).strip()
    err = None
    if len(username) < 2:
        err = "Bitte einen Namen mit mindestens 2 Zeichen angeben."
    elif len(username) > 80:
        err = "Name ist zu lang (max. 80 Zeichen)."
    elif len(password) < 8:
        err = "Passwort mindestens 8 Zeichen."
    elif password != password2:
        err = "Passwörter stimmen nicht überein."
    if err:
        return templates.TemplateResponse(
            request,
            "registrierung.html",
            {"error": err},
            status_code=400,
        )
    if db.query(models.User).filter(models.User.username == username).first():
        return templates.TemplateResponse(
            request,
            "registrierung.html",
            {"error": "Dieser Name ist bereits registriert."},
            status_code=400,
        )
    db.add(
        models.User(
            username=username,
            password_hash=hash_password(password),
            display_name=username,
            is_approved=False,
            is_admin=False,
        ),
    )
    db.commit()
    return RedirectResponse("/login?registered=1", status_code=302)


@app.get("/admin/freigaben", response_class=HTMLResponse)
def admin_freigaben(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: AdminUser,
):
    pending = (
        db.query(models.User)
        .filter(models.User.is_approved.is_(False))
        .order_by(models.User.created_at.asc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin_freigaben.html",
        {"user": user, "pending": pending},
    )


@app.post("/admin/freigaben/{user_id}/genehmigen")
def admin_freigabe_genehmigen(
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: AdminUser,
):
    u = db.get(models.User, user_id)
    if u and not u.is_approved:
        u.is_approved = True
        db.commit()
    return RedirectResponse("/admin/freigaben", status_code=302)


@app.post("/admin/freigaben/{user_id}/ablehnen")
def admin_freigabe_ablehnen(
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: AdminUser,
):
    u = db.get(models.User, user_id)
    if u and not u.is_approved and not u.is_admin:
        db.delete(u)
        db.commit()
    return RedirectResponse("/admin/freigaben", status_code=302)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


def _termin_list_rows(db: Session, user: models.User) -> list[dict]:
    rows = (
        db.query(models.Termin)
        .options(
            selectinload(models.Termin.teilnahmen).selectinload(
                models.TerminTeilnahme.user
            ),
        )
        .order_by(models.Termin.starts_at.asc())
        .all()
    )
    out = []
    for t in rows:
        names = sorted(
            {
                (tn.user.display_name or tn.user.username).strip()
                for tn in t.teilnahmen
            },
            key=str.lower,
        )
        ich = any(tn.user_id == user.id for tn in t.teilnahmen)
        kann = _can_manage_termin(user, t)
        out.append(
            {
                "termin": t,
                "teilnehmer": names,
                "ich_teilnehme": ich,
                "kann_verwalten": kann,
            },
        )
    return out


@app.get("/termine", response_class=HTMLResponse)
def termine_list(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
):
    termin_rows = _termin_list_rows(db, user)
    token = ensure_ics_token_for_ui(db, ICS_TOKEN)
    base = str(request.base_url).rstrip("/")
    feed_url = f"{base}/calendar.ics?t={token}"
    pending_count = 0
    if user.is_admin:
        pending_count = (
            db.query(models.User)
            .filter(models.User.is_approved.is_(False))
            .count()
        )
    return templates.TemplateResponse(
        request,
        "termine_list.html",
        {
            "user": user,
            "termin_rows": termin_rows,
            "feed_url": feed_url,
            "pending_count": pending_count,
        },
    )


@app.post("/termine/{termin_id}/teilnehmen")
def termin_teilnehmen(
    termin_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
):
    t = db.get(models.Termin, termin_id)
    if not t:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    exists = (
        db.query(models.TerminTeilnahme)
        .filter_by(termin_id=termin_id, user_id=user.id)
        .first()
    )
    if not exists:
        db.add(
            models.TerminTeilnahme(termin_id=termin_id, user_id=user.id),
        )
        db.commit()
    return RedirectResponse("/termine", status_code=302)


@app.post("/termine/{termin_id}/abmelden")
@app.post("/termine/{termin_id}/absagen")
def termin_abmelden(
    termin_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
):
    row = (
        db.query(models.TerminTeilnahme)
        .filter_by(termin_id=termin_id, user_id=user.id)
        .first()
    )
    if row:
        db.delete(row)
        db.commit()
    return RedirectResponse("/termine", status_code=302)


@app.get("/termine/neu", response_class=HTMLResponse)
def termin_new_form(request: Request, user: CurrentUser):
    return templates.TemplateResponse(
        request,
        "termin_form.html",
        {
            "user": user,
            "termin": None,
            "error": None,
            "max_mb": MAX_UPLOAD_MB,
        },
    )


@app.post("/termine/neu", response_class=HTMLResponse)
async def termin_create(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    title: Annotated[str, Form()],
    datum: Annotated[date, Form()],
    start_uhrzeit: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "",
    end_uhrzeit: Annotated[str, Form()] = "",
    bild: Annotated[Optional[UploadFile], File()] = None,
):
    err = _parse_times(start_uhrzeit, end_uhrzeit)
    if err:
        return templates.TemplateResponse(
            request,
            "termin_form.html",
            {
                "user": user,
                "termin": None,
                "error": err,
                "max_mb": MAX_UPLOAD_MB,
            },
            status_code=400,
        )
    st = _combine(datum, start_uhrzeit)
    en = _combine(datum, end_uhrzeit) if end_uhrzeit.strip() else None
    if en and en <= st:
        en = None

    t = models.Termin(
        title=title.strip(),
        description=description.strip(),
        location=location.strip(),
        starts_at=st,
        ends_at=en,
        created_by_id=user.id,
    )
    db.add(t)
    db.flush()

    if bild and bild.filename:
        ext = _safe_ext(bild.filename, bild.content_type)
        if ext and bild.content_type in ALLOWED_IMAGE:
            max_b = MAX_UPLOAD_MB * 1024 * 1024
            dest_name = f"{t.id}_{uuid.uuid4().hex}{ext}"
            dest = UPLOAD_DIR / dest_name
            size = 0
            with dest.open("wb") as f:
                while chunk := await bild.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_b:
                        dest.unlink(missing_ok=True)
                        return templates.TemplateResponse(
                            request,
                            "termin_form.html",
                            {
                                "user": user,
                                "termin": None,
                                "error": f"Bild zu groß (max. {MAX_UPLOAD_MB} MB).",
                                "max_mb": MAX_UPLOAD_MB,
                            },
                            status_code=400,
                        )
                    f.write(chunk)
            t.image_path = dest_name
            db.add(t)

    db.commit()
    return RedirectResponse("/termine", status_code=302)


@app.get("/termine/{termin_id}/bearbeiten", response_class=HTMLResponse)
def termin_edit_form(
    termin_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
):
    t = db.get(models.Termin, termin_id)
    if not t:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    if not _can_manage_termin(user, t):
        raise HTTPException(
            status_code=403,
            detail="Du darfst diesen Termin nicht bearbeiten.",
        )
    return templates.TemplateResponse(
        request,
        "termin_form.html",
        {
            "user": user,
            "termin": t,
            "error": None,
            "max_mb": MAX_UPLOAD_MB,
        },
    )


@app.post("/termine/{termin_id}/bearbeiten", response_class=HTMLResponse)
async def termin_edit_save(
    termin_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    title: Annotated[str, Form()],
    datum: Annotated[date, Form()],
    start_uhrzeit: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "",
    end_uhrzeit: Annotated[str, Form()] = "",
    bild_entfernen: Annotated[str, Form()] = "",
    bild: Annotated[Optional[UploadFile], File()] = None,
):
    t = db.get(models.Termin, termin_id)
    if not t:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    if not _can_manage_termin(user, t):
        raise HTTPException(
            status_code=403,
            detail="Du darfst diesen Termin nicht bearbeiten.",
        )

    err = _parse_times(start_uhrzeit, end_uhrzeit)
    if err:
        return templates.TemplateResponse(
            request,
            "termin_form.html",
            {
                "user": user,
                "termin": t,
                "error": err,
                "max_mb": MAX_UPLOAD_MB,
            },
            status_code=400,
        )
    st = _combine(datum, start_uhrzeit)
    en = _combine(datum, end_uhrzeit) if end_uhrzeit.strip() else None
    if en and en <= st:
        en = None

    t.title = title.strip()
    t.description = description.strip()
    t.location = location.strip()
    t.starts_at = st
    t.ends_at = en

    if bild_entfernen == "1":
        _unlink_upload(t.image_path)
        t.image_path = None

    if bild and bild.filename:
        ext = _safe_ext(bild.filename, bild.content_type)
        if ext and bild.content_type in ALLOWED_IMAGE:
            max_b = MAX_UPLOAD_MB * 1024 * 1024
            dest_name = f"{t.id}_{uuid.uuid4().hex}{ext}"
            dest = UPLOAD_DIR / dest_name
            size = 0
            with dest.open("wb") as f:
                while chunk := await bild.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_b:
                        dest.unlink(missing_ok=True)
                        db.rollback()
                        db.refresh(t)
                        return templates.TemplateResponse(
                            request,
                            "termin_form.html",
                            {
                                "user": user,
                                "termin": t,
                                "error": f"Bild zu groß (max. {MAX_UPLOAD_MB} MB).",
                                "max_mb": MAX_UPLOAD_MB,
                            },
                            status_code=400,
                        )
                    f.write(chunk)
            _unlink_upload(t.image_path)
            t.image_path = dest_name

    db.add(t)
    db.commit()
    return RedirectResponse("/termine", status_code=302)


@app.get("/termine/{termin_id}/loeschen", response_class=HTMLResponse)
def termin_delete_confirm(
    termin_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
):
    t = db.get(models.Termin, termin_id)
    if not t:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    if not _can_manage_termin(user, t):
        raise HTTPException(
            status_code=403,
            detail="Du darfst diesen Termin nicht löschen.",
        )
    return templates.TemplateResponse(
        request,
        "termin_loeschen.html",
        {"user": user, "termin": t},
    )


@app.post("/termine/{termin_id}/loeschen")
def termin_delete_do(
    termin_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
):
    t = db.get(models.Termin, termin_id)
    if not t:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    if not _can_manage_termin(user, t):
        raise HTTPException(
            status_code=403,
            detail="Du darfst diesen Termin nicht löschen.",
        )
    _unlink_upload(t.image_path)
    db.delete(t)
    db.commit()
    return RedirectResponse("/termine", status_code=302)


_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")


def _parse_times(start_s: str, end_s: str) -> str | None:
    if not _TIME_RE.match(start_s or ""):
        return "Start-Uhrzeit bitte als HH:MM angeben."
    if end_s.strip() and not _TIME_RE.match(end_s):
        return "End-Uhrzeit bitte als HH:MM angeben oder leer lassen."
    return None


def _combine(d: date, hhmm: str) -> datetime:
    m = _TIME_RE.match(hhmm.strip())
    assert m
    h, mi = int(m.group(1)), int(m.group(2))
    return datetime(d.year, d.month, d.day, h, mi, 0)


@app.get("/calendar.ics")
def calendar_ics(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    t: Optional[str] = None,
):
    if not verify_ics_token(db, ICS_TOKEN, t):
        raise HTTPException(status_code=404, detail="Not found")
    termine = all_termine_for_feed(db)
    body = build_ics_calendar(termine)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="wahlkampf.ics"',
            "Cache-Control": "no-store",
        },
    )
