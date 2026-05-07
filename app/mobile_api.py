"""JSON-API für native Clients (SwiftUI) — gleiche Session-Cookies wie die Web-App."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import verify_password
from app.config import is_superadmin_username
from app.deps import CurrentUser, get_current_user
from app.platform_database import get_platform_db
from app.platform_models import (
    MandantAppSetting,
    Ortsverband,
    OvMembership,
    PlatformUser,
    Termin,
    TerminKommentar,
    TerminTeilnahme,
)
from app.platform_models import TEILNAHME_STATUS_ABGESAGT, TEILNAHME_STATUS_ZUGESAGT

router = APIRouter()


class MobileLoginBody(BaseModel):
    username: str = Field("", max_length=200)
    password: str = Field("", max_length=500)


class KommentarBody(BaseModel):
    body: str = Field("", max_length=4000)


def _termin_core_dict(t: Termin) -> dict[str, Any]:
    return {
        "id": t.id,
        "mandant_slug": t.mandant_slug.strip().lower(),
        "title": t.title,
        "description": t.description or "",
        "location": t.location or "",
        "starts_at": t.starts_at.isoformat(),
        "ends_at": t.ends_at.isoformat() if t.ends_at else None,
        "link_url": t.link_url,
        "termin_kategorie": (getattr(t, "termin_kategorie", None) or "verband").strip().lower(),
        "promoted_all_ovs": bool(getattr(t, "promoted_all_ovs", False)),
        "image_path": t.image_path,
    }


def _termin_row_api(
    row: dict[str, Any],
    *,
    request: Request,
    kommentar_count: int | None = None,
) -> dict[str, Any]:
    """Aus Template-Row (mit ORM-Termin) ein JSON-Objekt bauen."""
    t: Termin = row["termin"]
    base = str(request.base_url).rstrip("/")
    mp_row = (row.get("mandanten_prefix") or f"/m/{t.mandant_slug.strip().lower()}").rstrip(
        "/"
    )
    rel_media = ""
    if t.image_path:
        rel_media = f"{mp_row}/media/{t.image_path}"
    out = {
        "termin": _termin_core_dict(t),
        "ov_display_name": row.get("ov_display_name") or "",
        "mandanten_prefix": mp_row,
        "teilnehmer": row.get("teilnehmer") or [],
        "teilnehmer_abgesagt": row.get("teilnehmer_abgesagt") or [],
        "teilnehmer_extern": row.get("teilnehmer_extern") or [],
        "ich_teilnehme": bool(row.get("ich_teilnehme")),
        "ich_abgesagt": bool(row.get("ich_abgesagt")),
        "kann_verwalten": bool(row.get("kann_verwalten")),
        "kommentar_count": kommentar_count
        if kommentar_count is not None
        else int(row.get("kommentar_count") or 0),
        "termin_kategorie_label": row.get("termin_kategorie_label") or "",
        "termin_web_prefix": row.get("termin_web_prefix") or "termine",
        "detail_path": f"{mp_row}/{row.get('termin_web_prefix') or 'termine'}/{t.id}",
        "image_url": f"{base}{rel_media}" if rel_media else None,
    }
    return out


@router.post("/auth/login")
def mobile_auth_login(
    mandant_slug: str,
    request: Request,
    body: MobileLoginBody,
    pdb: Session = Depends(get_platform_db),
):
    """Session setzen wie Web-Login; Client speichert Cookie (URLSession)."""
    ms = mandant_slug.strip().lower()
    if pdb.get(Ortsverband, ms) is None:
        raise HTTPException(status_code=404, detail="Ortsverband unbekannt.")
    uname = body.username.strip().lower()
    pu = (
        pdb.query(PlatformUser)
        .filter(func.lower(PlatformUser.username) == uname)
        .first()
    )
    if not pu or not verify_password(body.password, pu.password_hash):
        raise HTTPException(status_code=401, detail="Benutzername oder Passwort falsch.")
    mem = (
        pdb.query(OvMembership)
        .filter(OvMembership.user_id == pu.id, OvMembership.ov_slug == ms)
        .first()
    )
    if not is_superadmin_username(pu.username):
        if mem is None:
            raise HTTPException(
                status_code=403,
                detail="Für diesen Ortsverband noch nicht freigeschaltet.",
            )
        if not mem.is_approved:
            has_active_admin = (
                pdb.query(OvMembership)
                .filter(
                    OvMembership.ov_slug == ms,
                    OvMembership.is_admin.is_(True),
                    OvMembership.is_approved.is_(True),
                )
                .first()
            )
            if not has_active_admin:
                mem.is_approved = True
                mem.is_admin = True
                pdb.merge(
                    MandantAppSetting(mandant_slug=ms, key="founder_done", value="1")
                )
                pdb.commit()
            else:
                raise HTTPException(
                    status_code=403,
                    detail="Konto noch nicht freigegeben. Bitte Administrator kontaktieren.",
                )
    request.session["user_id"] = pu.id
    request.session["mandant_slug"] = ms
    return JSONResponse(
        {
            "ok": True,
            "user": {
                "id": pu.id,
                "username": pu.username,
                "display_name": (pu.display_name or "").strip() or pu.username,
            },
            "mandant_slug": ms,
        }
    )


@router.post("/auth/logout")
def mobile_auth_logout(mandant_slug: str, request: Request):
    request.session.pop("user_id", None)
    request.session.pop("mandant_slug", None)
    return JSONResponse({"ok": True})


@router.get("/me")
def mobile_me(
    mandant_slug: str,
    user: CurrentUser,
    pdb: Session = Depends(get_platform_db),
):
    ms = mandant_slug.strip().lower()
    mem = user.membership
    ov = pdb.get(Ortsverband, ms)
    return JSONResponse(
        {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
            "mandant_slug": ms,
            "ortsverband_name": ((ov.display_name or "").strip() or ms) if ov else ms,
            "is_admin": user.is_admin,
            "membership_approved": bool(mem and mem.is_approved),
            "vorstand_member": bool(mem and mem.vorstand_member),
            "fraktion_member": bool(mem and mem.fraktion_member),
            "platform_superadmin": is_superadmin_username(user.username),
        }
    )


@router.get("/termine")
def mobile_termine_list(
    mandant_slug: str,
    request: Request,
    pdb: Session = Depends(get_platform_db),
    user: CurrentUser = Depends(get_current_user),
):
    from app.main import _split_termine_upcoming_past, _termin_list_rows

    rows = _termin_list_rows(pdb, mandant_slug, user)
    upcoming, past = _split_termine_upcoming_past(rows)
    return JSONResponse(
        {
            "upcoming": [_termin_row_api(r, request=request) for r in upcoming],
            "past": [_termin_row_api(r, request=request) for r in past],
        }
    )


@router.get("/termine/{termin_id}")
def mobile_termin_detail(
    mandant_slug: str,
    termin_id: int,
    request: Request,
    pdb: Session = Depends(get_platform_db),
    user: CurrentUser = Depends(get_current_user),
):
    from app.main import (
        _termin_detail_row,
        _termin_kommentare_public,
        ensure_user_calendar_token,
        _mp,
    )

    row = _termin_detail_row(pdb, mandant_slug, user, termin_id)
    if not row:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    t = row["termin"]
    kommentare = _termin_kommentare_public(pdb, termin_id, user, termin=t)
    base = str(request.base_url).rstrip("/")
    my_token = ensure_user_calendar_token(pdb, user.platform_user)
    mp = _mp(request)
    feed_my = f"{base}{mp}/calendar/zusagen-alle.ics?t={my_token}"
    feed_all = f"{base}{mp}/calendar/termine-alle.ics?t={my_token}"
    termin_vergangen = t.starts_at < datetime.utcnow()
    return JSONResponse(
        {
            "row": _termin_row_api(row, request=request),
            "kommentare": kommentare,
            "termin_vergangen": termin_vergangen,
            "calendar_feed_zugesagt_url": feed_my,
            "calendar_feed_alle_url": feed_all,
        }
    )


@router.post("/termine/{termin_id}/kommentare")
def mobile_kommentar_create(
    mandant_slug: str,
    termin_id: int,
    payload: KommentarBody,
    request: Request,
    pdb: Session = Depends(get_platform_db),
    user: CurrentUser = Depends(get_current_user),
):
    from app.main import _termin_kommentare_public, termin_sichtbar_in_mandant

    body_txt = payload.body.strip()
    if not body_txt:
        raise HTTPException(status_code=400, detail="Kommentar darf nicht leer sein.")
    ms = mandant_slug.strip().lower()
    t = termin_sichtbar_in_mandant(pdb, termin_id, ms, user)
    if not t:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden.")
    km = TerminKommentar(
        termin_id=termin_id,
        user_id=user.id,
        body=body_txt[:4000],
    )
    pdb.add(km)
    pdb.commit()
    return JSONResponse(
        {
            "ok": True,
            "kommentare": _termin_kommentare_public(pdb, termin_id, user, termin=t),
        }
    )


@router.post("/termine/{termin_id}/teilnehmen")
def mobile_termin_teilnehmen(
    mandant_slug: str,
    termin_id: int,
    request: Request,
    pdb: Session = Depends(get_platform_db),
    user: CurrentUser = Depends(get_current_user),
):
    from app.main import (
        _termin_detail_row,
        termin_sichtbar_in_mandant,
        _termin_row_api,
    )

    ms = mandant_slug.strip().lower()
    t = termin_sichtbar_in_mandant(pdb, termin_id, ms, user)
    if not t:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    exists = (
        pdb.query(TerminTeilnahme)
        .filter_by(termin_id=termin_id, user_id=user.id)
        .first()
    )
    if not exists:
        pdb.add(
            TerminTeilnahme(
                termin_id=termin_id,
                user_id=user.id,
                teilnahme_status=TEILNAHME_STATUS_ZUGESAGT,
            )
        )
    else:
        exists.teilnahme_status = TEILNAHME_STATUS_ZUGESAGT
        pdb.add(exists)
    pdb.commit()
    row = _termin_detail_row(pdb, mandant_slug, user, termin_id)
    if not row:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    return JSONResponse({"ok": True, "row": _termin_row_api(row, request=request)})


@router.post("/termine/{termin_id}/absagen")
def mobile_termin_absagen(
    mandant_slug: str,
    termin_id: int,
    request: Request,
    pdb: Session = Depends(get_platform_db),
    user: CurrentUser = Depends(get_current_user),
):
    from app.main import _termin_detail_row, termin_sichtbar_in_mandant, _termin_row_api

    ms = mandant_slug.strip().lower()
    t = termin_sichtbar_in_mandant(pdb, termin_id, ms, user)
    if not t:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    row_tn = (
        pdb.query(TerminTeilnahme)
        .filter_by(termin_id=termin_id, user_id=user.id)
        .first()
    )
    if row_tn:
        row_tn.teilnahme_status = TEILNAHME_STATUS_ABGESAGT
        pdb.add(row_tn)
    else:
        pdb.add(
            TerminTeilnahme(
                termin_id=termin_id,
                user_id=user.id,
                teilnahme_status=TEILNAHME_STATUS_ABGESAGT,
            )
        )
    pdb.commit()
    row = _termin_detail_row(pdb, mandant_slug, user, termin_id)
    if not row:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    return JSONResponse({"ok": True, "row": _termin_row_api(row, request=request)})


@router.get("/menu")
def mobile_menu_summary(
    mandant_slug: str,
    request: Request,
    pdb: Session = Depends(get_platform_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Kompakte Übersicht analog Web-Menü (Tabs / Deep Links)."""
    from app.main import (
        _href_under_ov,
        _menu_show_alle_termine,
        _mp,
        _my_ovs_menu_items,
    )

    ms = mandant_slug.strip().lower()
    my_ovs = _my_ovs_menu_items(pdb, mandant_slug, user.id, user.username)
    tabs: list[dict[str, Any]] = [
        {
            "id": "termine",
            "title": "Termine",
            "href": _href_under_ov(request, ms, "termine"),
            "api": _href_under_ov(request, ms, "api/v1/termine"),
        }
    ]
    for o in my_ovs:
        if not o.get("has_feature_links"):
            continue
        slug = o["slug"]
        if not o.get("feature_plakate", True):
            continue
        tabs.append(
            {
                "id": f"plakate-{slug}",
                "title": f"Plakate · {o.get('display_name') or slug}",
                "href": _href_under_ov(request, slug, "plakate"),
                "api_list": _href_under_ov(request, slug, "plakate/api/list"),
            }
        )
    tabs.append(
        {
            "id": "profil",
            "title": "Profil / Konto",
            "href": _href_under_ov(request, ms, "profil"),
        }
    )
    return JSONResponse(
        {
            "mandanten_prefix": _mp(request),
            "show_alle_termine": _menu_show_alle_termine(pdb, user),
            "my_ovs": my_ovs,
            "tabs": tabs,
        }
    )
