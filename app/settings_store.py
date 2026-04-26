from __future__ import annotations

import secrets
from typing import Optional

from sqlalchemy.orm import Session

from app import models


ICS_KEY = "ics_token"


def ics_token_value(db: Session, env_token: str) -> str | None:
    if env_token.strip():
        return env_token.strip()
    row = db.get(models.AppSetting, ICS_KEY)
    return row.value if row else None


def ensure_ics_token_for_ui(db: Session, env_token: str) -> str:
    if env_token.strip():
        return env_token.strip()
    row = db.get(models.AppSetting, ICS_KEY)
    if row:
        return row.value
    token = secrets.token_urlsafe(32)
    db.add(models.AppSetting(key=ICS_KEY, value=token))
    db.commit()
    return token


def verify_ics_token(db: Session, env_token: str, provided: Optional[str]) -> bool:
    if not provided:
        return False
    expected = ics_token_value(db, env_token)
    if not expected:
        return False
    return secrets.compare_digest(provided, expected)
