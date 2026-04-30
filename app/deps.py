from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import SUPERADMIN_USERNAME
from app.database import get_db
from app.models import User


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    uid = request.session.get("user_id")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht angemeldet",
        )
    user = db.get(User, int(uid))
    if not user:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sitzung ungültig",
        )
    if not user.is_approved:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Konto noch nicht freigegeben.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_admin_user(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur für Administratoren.",
        )
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]


def require_letzgo_superadmin(user: CurrentUser) -> User:
    if user.username.strip().lower() != SUPERADMIN_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Nur für den Superadmin (Benutzer „{SUPERADMIN_USERNAME}“).",
        )
    return user


LetzgoSuperadmin = Annotated[User, Depends(require_letzgo_superadmin)]
