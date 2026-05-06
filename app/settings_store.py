from __future__ import annotations

import secrets
from typing import Optional

from sqlalchemy.orm import Session

from app.platform_models import MandantAppSetting, PlatformUser

ICS_KEY = "ics_token"
SHAREPIC_SLOGAN_DEFAULT_KEY = "sharepic_slogan_default"


def ics_token_value(pdb: Session, mandant_slug: str, env_token: str) -> str | None:
    if env_token.strip():
        return env_token.strip()
    slug = mandant_slug.strip().lower()
    row = pdb.get(MandantAppSetting, (slug, ICS_KEY))
    return row.value if row else None


def ensure_ics_token_for_ui(pdb: Session, mandant_slug: str, env_token: str) -> str:
    if env_token.strip():
        return env_token.strip()
    slug = mandant_slug.strip().lower()
    row = pdb.get(MandantAppSetting, (slug, ICS_KEY))
    if row:
        return row.value
    token = secrets.token_urlsafe(32)
    pdb.add(MandantAppSetting(mandant_slug=slug, key=ICS_KEY, value=token))
    pdb.commit()
    return token


def verify_ics_token(
    pdb: Session,
    mandant_slug: str,
    env_token: str,
    provided: Optional[str],
) -> bool:
    if not provided:
        return False
    expected = ics_token_value(pdb, mandant_slug, env_token)
    if not expected:
        return False
    return secrets.compare_digest(provided, expected)


def ensure_user_calendar_token(pdb: Session, user: PlatformUser) -> str:
    """Geheimer Token für den persönlichen Kalender-Feed (nur zugesagte Termine)."""
    if user.calendar_token:
        return user.calendar_token
    for _ in range(24):
        token = secrets.token_urlsafe(18)
        clash = (
            pdb.query(PlatformUser)
            .filter(PlatformUser.calendar_token == token)
            .first()
        )
        if not clash:
            user.calendar_token = token
            pdb.commit()
            pdb.refresh(user)
            return token
    raise RuntimeError("Kalender-Token konnte nicht erzeugt werden.")


def _default_sharepic_slogan(ov_display_name: str) -> str:
    ovn = (ov_display_name or "").strip() or "deinen Verband"
    return f"Für {ovn}.\nFür Dich."


def sharepic_slogan_default_value(
    pdb: Session,
    mandant_slug: str,
    ov_display_name: str,
) -> str:
    slug = mandant_slug.strip().lower()
    row = pdb.get(MandantAppSetting, (slug, SHAREPIC_SLOGAN_DEFAULT_KEY))
    if row and (row.value or "").strip():
        return row.value
    return _default_sharepic_slogan(ov_display_name)


def save_sharepic_slogan_default(
    pdb: Session,
    mandant_slug: str,
    slogan: str,
) -> None:
    slug = mandant_slug.strip().lower()
    raw = (slogan or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in raw.split("\n")]
    normalized = "\n".join(lines).strip()
    if len(normalized) > 500:
        normalized = normalized[:500].rstrip()
    row = pdb.get(MandantAppSetting, (slug, SHAREPIC_SLOGAN_DEFAULT_KEY))
    if normalized:
        pdb.merge(
            MandantAppSetting(
                mandant_slug=slug,
                key=SHAREPIC_SLOGAN_DEFAULT_KEY,
                value=normalized,
            )
        )
        return
    if row:
        pdb.delete(row)
