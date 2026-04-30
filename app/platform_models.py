from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class PlatformBase(DeclarativeBase):
    pass


class PlatformUser(PlatformBase):
    """Superadmin (plattformweit), nicht mit OV-Nutzern zu verwechseln."""

    __tablename__ = "platform_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Ortsverband(PlatformBase):
    """Registrierter Ortsverband (Slug = URL-Pfad unter /m/<slug>/)."""

    __tablename__ = "ortsverbaende"

    slug: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
