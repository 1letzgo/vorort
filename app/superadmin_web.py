from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

from app.deps import LetzgoSuperadmin
from app.ov_services import (
    register_ortsverband,
    save_uploaded_sharepic_mask,
    validate_ov_slug,
)
from app.platform_database import get_platform_db
from app.platform_models import Ortsverband

TEMPLATES_DIR = __import__("pathlib").Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["superadmin"])


@router.get("/admin", include_in_schema=False)
def superadmin_root():
    return RedirectResponse("/admin/ortsverbaende", status_code=302)


@router.get("/admin/ortsverbaende", response_class=HTMLResponse)
def superadmin_ov_list(
    request: Request,
    db: Annotated[Session, Depends(get_platform_db)],
    _: LetzgoSuperadmin,
):
    ovs = db.query(Ortsverband).order_by(Ortsverband.slug.asc()).all()
    return templates.TemplateResponse(
        request,
        "superadmin_ovs.html",
        {"ovs": ovs},
    )


@router.get("/admin/ortsverbaende/neu", response_class=HTMLResponse)
def superadmin_ov_new_form(
    request: Request,
    _: LetzgoSuperadmin,
):
    return templates.TemplateResponse(
        request,
        "superadmin_ov_form.html",
        {"error": None, "ov": None, "is_new": True},
    )


@router.post("/admin/ortsverbaende/neu", response_class=HTMLResponse)
async def superadmin_ov_new_submit(
    request: Request,
    db: Annotated[Session, Depends(get_platform_db)],
    _: LetzgoSuperadmin,
    slug: Annotated[str, Form()],
    display_name: Annotated[str, Form()],
    mask: Annotated[Optional[UploadFile], File()] = None,
):
    err = validate_ov_slug(slug)
    if err:
        return templates.TemplateResponse(
            request,
            "superadmin_ov_form.html",
            {"error": err, "ov": None, "is_new": True},
            status_code=400,
        )
    s = slug.strip().lower()
    if db.get(Ortsverband, s):
        return templates.TemplateResponse(
            request,
            "superadmin_ov_form.html",
            {"error": "Dieser Slug existiert bereits.", "ov": None, "is_new": True},
            status_code=400,
        )
    register_ortsverband(db, s, display_name)
    if mask and mask.filename:
        try:
            save_uploaded_sharepic_mask(s, mask)
        except ValueError as e:
            return templates.TemplateResponse(
                request,
                "superadmin_ov_form.html",
                {"error": str(e), "ov": None, "is_new": True},
                status_code=400,
            )
    return RedirectResponse("/admin/ortsverbaende", status_code=302)


@router.get("/admin/ortsverbaende/{slug}/bearbeiten", response_class=HTMLResponse)
def superadmin_ov_edit_form(
    slug: str,
    request: Request,
    db: Annotated[Session, Depends(get_platform_db)],
    _: LetzgoSuperadmin,
):
    ov = db.get(Ortsverband, slug.strip().lower())
    if not ov:
        raise HTTPException(status_code=404, detail="Unbekannt")
    return templates.TemplateResponse(
        request,
        "superadmin_ov_form.html",
        {"error": None, "ov": ov, "is_new": False},
    )


@router.post("/admin/ortsverbaende/{slug}/bearbeiten", response_class=HTMLResponse)
async def superadmin_ov_edit_submit(
    slug: str,
    request: Request,
    db: Annotated[Session, Depends(get_platform_db)],
    _: LetzgoSuperadmin,
    display_name: Annotated[str, Form()],
    mask: Annotated[Optional[UploadFile], File()] = None,
):
    ov = db.get(Ortsverband, slug.strip().lower())
    if not ov:
        raise HTTPException(status_code=404, detail="Unbekannt")
    ov.display_name = " ".join(display_name.split()).strip() or ov.slug
    db.add(ov)
    db.commit()
    if mask and mask.filename:
        try:
            save_uploaded_sharepic_mask(ov.slug, mask)
        except ValueError as e:
            return templates.TemplateResponse(
                request,
                "superadmin_ov_form.html",
                {"error": str(e), "ov": ov, "is_new": False},
                status_code=400,
            )
    return RedirectResponse("/admin/ortsverbaende", status_code=302)
