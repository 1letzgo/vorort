"""Pro-Mandant aktivierbare Funktionen (Schalter für Superadmins)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.platform_models import MandantAppSetting

FEATURE_PLAKATE = "feature_plakate"
FEATURE_SHAREPIC = "feature_sharepic"
FEATURE_FRAKTION = "feature_fraktion"
FEATURE_AUFGABEN = "feature_aufgaben"

_FEATURE_DEFAULT_ENABLED: dict[str, bool] = {
    FEATURE_AUFGABEN: False,
}


def is_mandant_feature_enabled(
    pdb: Session,
    mandant_slug: str,
    key: str,
    *,
    default: bool | None = None,
) -> bool:
    """Kein Eintrag oder leer → default (pro Key aus _FEATURE_DEFAULT_ENABLED, sonst True)."""
    ms = mandant_slug.strip().lower()
    row = pdb.get(MandantAppSetting, (ms, key))
    eff_default = default if default is not None else _FEATURE_DEFAULT_ENABLED.get(key, True)
    if row is None:
        return eff_default
    v = (row.value or "").strip().lower()
    if v in ("0", "false", "off", "no", ""):
        return False
    return True


def merge_mandant_feature(pdb: Session, mandant_slug: str, key: str, enabled: bool) -> None:
    ms = mandant_slug.strip().lower()
    pdb.merge(MandantAppSetting(mandant_slug=ms, key=key, value="1" if enabled else "0"))
