# Patch: Termine-/Aufgaben-/Admin-Menü auf Dropdowns umstellen (V7)

Ersetzt die bisherige `.kalender-nav-leiste` (OV-Tab-Strip + Gruppen-Pill-Bar) durch
**zwei nebeneinander stehende Dropdowns** (OV + Gruppe) bzw. ein einzelnes
OV-Dropdown im Admin-Hub. Funktional unverändert — gleiche URL-Parameter
(`?tab=`, `?gruppe=`), gleiche Server-Daten (`termin_tabs`, `aufgaben_tabs`,
`admin_tabs`, `gruppe_tabs`).

## Dateien

| Aktion | Pfad |
|---|---|
| **neu** | `app/static/kalender-nav.js` |
| **edit** | `app/static/app.css` *(Block aus `_kalender-nav.css` anhängen)* |
| **edit** | `app/templates/_ui_macros.html` *(Macro `kalender_nav_dropdowns` hinzu)* |
| **edit** | `app/templates/base.html` *(eine Zeile: Script-Include)* |
| **edit** | `app/templates/termine_list.html` |
| **edit** | `app/templates/aufgaben_list.html` |
| **edit** | `app/templates/administration_hub.html` |

Alles unter `patch/app/...` ist 1:1 fertig zum Rüberkopieren.

## Schritte

1. **`app/static/kalender-nav.js`** komplett neu anlegen *(aus `patch/app/static/kalender-nav.js`)*.
2. **`app/static/app.css`** öffnen, ans Ende den Block aus `patch/app/static/_kalender-nav.css` anhängen (Datei beginnt unter dem Kopfkommentar — alles ab `/* ─── Kalender-Navigation als zwei Dropdowns ──────────────────────────── */` übernehmen).
   *Optional:* Du kannst danach die alten Regeln für `.kalender-nav-leiste`, `.kalender-nav-leiste__submenu`, `.kalender-gruppe-bar*`, sowie die ergänzenden `.kalender-nav-leiste .termin-tab[…]`-Regeln entfernen. Die Basis-`.termin-tab`/`.termin-tablist`-Regeln bleiben besser stehen, falls sie an anderer Stelle (z. B. Admin-Hub vor diesem Patch, Tests, externe Seiten) noch genutzt werden.
3. **`app/templates/_ui_macros.html`** ersetzen *(neu: Macro `kalender_nav_dropdowns`)*.
4. **`app/templates/base.html`** ersetzen *(eine zusätzliche `<script defer src=".../static/kalender-nav.js">`-Zeile, sonst unverändert)*.
5. **`app/templates/termine_list.html`**, **`aufgaben_list.html`**, **`administration_hub.html`** ersetzen.

## Was hat sich an der Server-API geändert?

**Nichts.** `_kalender_gruppe_tab_defs()`, `_build_termin_tabs_for_user()`,
`_build_aufgaben_tabs_for_user()` und die Admin-Hub-Tab-Erzeugung liefern
weiterhin Listen mit `id`/`label`. Der `admin_pending_count` wird im
OV-Option-Menü als Badge dargestellt (war vorher als `(N)` im Tab-Label).

## Was hat sich an der URL gegenüber vorher geändert?

**Nichts.** Tab-Wechsel im OV-Dropdown setzt `?tab=…` per
`history.replaceState`, Gruppen-Wechsel macht weiterhin einen vollen Reload
mit `?gruppe=…`.

## A11y

- Buttons mit `aria-haspopup="listbox"`, `aria-expanded` togglet.
- Menü mit `role="listbox"`, jedes Item `role="option"` + `aria-selected`.
- Keyboard: Esc schließt, Pfeil ↑/↓ navigiert in offenem Menü, Enter/Space
  wählt.

## Stellen, die nicht angefasst wurden

- Termin-Karten-Layout / Footer / Anhänge etc.
- ICS-Abo-Dialog.
- Andere `.termin-tab`-Vorkommen (z. B. ältere Admin-Seiten) — die Klassen
  stehen weiterhin in `app.css` und funktionieren wie bisher. Wenn du sie
  auch ablösen willst, müssen sie einzeln auf das Macro umgestellt werden.

## Bekannte Limits / Folge-Tickets

- Sehr lange OV-Namen werden im Trigger per `ellipsis` gekürzt — Volltext
  bleibt im Menü sichtbar. Falls erwünscht: Trigger umbrechen lassen
  (`white-space: normal; line-height: 1.2`) und `min-height` entfernen.
- Wenn ein User in **vielen** OVs Mitglied ist (>8), könnte das Menü länger
  werden — `max-height: 60vh; overflow-y: auto` ist bereits gesetzt.
