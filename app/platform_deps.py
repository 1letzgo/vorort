from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.platform_database import get_platform_db
from app.platform_models import PlatformUser


def get_platform_admin(
    request: Request,
    db: Annotated[Session, Depends(get_platform_db)],
) -> PlatformUser:
    uid = request.session.get("platform_admin_id")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Superadmin-Anmeldung erforderlich.",
        )
    u = db.get(PlatformUser, int(uid))
    if not u:
        request.session.pop("platform_admin_id", None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sitzung ungültig.",
        )
    return u


PlatformAdmin = Annotated[PlatformUser, Depends(get_platform_admin)]
