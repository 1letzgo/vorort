"""Gemeinsame Logik: Nutzer↔OV-Zuordnung (Superadmin + Mandanten-Admins)."""

from __future__ import annotations

from typing import List, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import is_superadmin_username
from app.platform_models import Ortsverband, OvMembership, PlatformUser

PASSWORD_MIN_PLATFORM_USER = 8


def form_ov_slug_list(raw: Optional[List[str] | str]) -> List[str]:
    """Checkbox-Werte: bei einem Eintrag liefert Starlette teils str statt list."""
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip().lower()
        return [s] if s else []
    out: List[str] = []
    for x in raw:
        if not x:
            continue
        s = str(x).strip().lower()
        if s:
            out.append(s)
    return out


def sync_ov_memberships_superadmin(
    db: Session,
    user_id: int,
    member_slugs: List[str],
    admin_slugs: set[str],
    vorstand_slugs: set[str],
    fraktion_slugs: set[str],
) -> None:
    """OV-Zuordnungen aus Superadmin-Sicht: immer freigegeben (`is_approved=True`)."""
    member_set = {s.strip().lower() for s in member_slugs if s and s.strip()}
    if not member_set:
        valid: set[str] = set()
    else:
        valid = {
            r[0].strip().lower()
            for r in db.query(Ortsverband.slug).filter(Ortsverband.slug.in_(member_set)).all()
        }
    member_set &= valid
    admin_set = {s.strip().lower() for s in admin_slugs} & member_set
    vorstand_set = {s.strip().lower() for s in vorstand_slugs} & member_set
    fraktion_set = {s.strip().lower() for s in fraktion_slugs} & member_set

    rows = db.query(OvMembership).filter(OvMembership.user_id == user_id).all()
    by_slug = {m.ov_slug.strip().lower(): m for m in rows}
    for slug in member_set:
        m = by_slug.pop(slug, None)
        if m:
            m.is_approved = True
            m.is_admin = slug in admin_set
            m.vorstand_member = slug in vorstand_set
            m.fraktion_member = slug in fraktion_set
            db.add(m)
        else:
            db.add(
                OvMembership(
                    user_id=user_id,
                    ov_slug=slug,
                    is_admin=slug in admin_set,
                    is_approved=True,
                    vorstand_member=slug in vorstand_set,
                    fraktion_member=slug in fraktion_set,
                )
            )
    for m in by_slug.values():
        db.delete(m)


def tenant_admin_update_membership_flags(
    db: Session,
    target_user_id: int,
    ov_slug: str,
    *,
    is_admin: bool,
    vorstand_member: bool,
    fraktion_member: bool,
) -> OvMembership | None:
    """Nur Rechte-Spalten einer bestehenden Mitgliedschaft (ohne andere OVs)."""
    ms = ov_slug.strip().lower()
    m = (
        db.query(OvMembership)
        .filter(OvMembership.user_id == target_user_id, OvMembership.ov_slug == ms)
        .first()
    )
    if not m:
        return None
    m.is_admin = is_admin
    m.vorstand_member = vorstand_member
    m.fraktion_member = fraktion_member
    db.add(m)
    return m


def show_superadmin_delete_link(request: Request, pu: PlatformUser) -> bool:
    if is_superadmin_username(pu.username):
        return False
    suid = request.session.get("user_id")
    if suid is None:
        return False
    try:
        return int(suid) != pu.id
    except (TypeError, ValueError):
        return False


def superadmin_user_form_template_ctx(
    request: Request,
    pu: PlatformUser,
    ovs: list,
    mem_by_slug: dict,
    *,
    error: Optional[str] = None,
    flash_ok: bool = False,
    tenant_mandant_slug: str | None = None,
    nutzer_admin_base: str = "/admin/nutzer",
) -> dict:
    return {
        "edit_user": pu,
        "ovs": ovs,
        "mem_by_slug": mem_by_slug,
        "error": error,
        "platform_superadmin": is_superadmin_username(pu.username),
        "flash_ok": flash_ok,
        "show_delete_link": show_superadmin_delete_link(request, pu),
        "tenant_mandant_slug": tenant_mandant_slug,
        "nutzer_admin_base": nutzer_admin_base,
    }
