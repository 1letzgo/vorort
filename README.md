# VorOrt — Wahlkampf-App

Mandantenfähige **FastAPI**-Webapp für die Organisation auf OV-Ebene: **Termine** (inkl. Fraktion), **Kalender-Feeds** (ICS), **Sharepic-Generator**, **Plakat-Karte** und zentrale **OV-/Nutzerverwaltung**. Pro Ortsverband (OV) gibt es eigene Daten unter konfigurierbarem Speicherpfad (SQLite + Datei-Uploads).

---

## Schnellstart (Docker)

```bash
cd /pfad/zum/projekt
# Empfohlen: SECRET_KEY und ggf. SUPERADMIN_USERNAME setzen (siehe Abschnitt Konfiguration)
docker compose up --build
```

Die App lauscht dann auf **Port 8000**. Datenbanken und Uploads liegen im Volume `wahlkampf-data` (unter `/data` im Container) — ohne Volume gehen Daten bei jedem neuen Container verloren.

**Wichtig:** Legt im laufenden System mindestens einen Plattform-Superadmin an (Benutzer in der DB, gleicher Benutzername wie in `SUPERADMIN_USERNAME` / `SUPERADMIN_USERNAMES`), damit ihr unter `/admin/…` Ortsverbände und Features pflegen könnt.

Lokaler Entwicklungslauf ohne Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

---

## URLs und Mandanten

- **Standard:** Jeder OV hat ein Präfix **`/m/<slug>/`** (Beispiel: `http://localhost:8000/m/westerstede/termine`).
- **Öffentliche Kurz-URL (optional):** Mit `PUBLIC_SITE_HOSTS` und `PUBLIC_SITE_MANDANT_SLUG` reicht auf der eingetragenen Domain ein Pfad wie `/login` ohne `/m/slug` (siehe Kommentare in `docker-compose.yml` und `app/config.py`).
- **Subdomain je Mandant (optional):** `MANDANT_HOST_BASE_DOMAIN` — z. B. `westerstede.localhost` → gleicher OV wie `slug`.

Technische Details zu allen Umgebungsvariablen stehen in `app/config.py` und in den Kommentaren von `docker-compose.yml`.

---

## Anmeldung und Rechte

1. **Registrierung:** Unter **`/m/<slug>/registrierung`** (bzw. öffentlicher Host ohne `/m/…`) könnt ihr euch registrieren.
2. **OV-Zugehörigkeit:** Unter **„Mein Konto“** beantragt ihr die Mitgliedschaft in einem Ortsverband. Ein **OV-Administrator** (oder Superadmin) muss die Mitgliedschaft freigeben (`is_approved`).
3. **OV-Admin:** Kann Nutzer im OV verwalten (über die OV-Administration in der App).
4. **Plattform-Superadmin:** Pflege der Ortsverbände, Feature-Schalter, Fraktions-Kalender-URL, Sharepic-Vorlagen-Slogan usw. unter **`/admin/…`** (Benutzername über Env, siehe oben).

---

## Termine

### Normale Termine anlegen

1. Meldet euch an und öffnet **Termine**.
2. **Neuer Termin** (sichtbar, wenn ihr im jeweiligen OV berechtigt seid).
3. Formular:
   - **Titel, Datum, Beginn** (Format `HH:MM`), optional **Ende**, **Ort**, **Beschreibung**.
   - **Link (optional):** z. B. RIS oder Videokonferenz — wird in Liste und Detailseite verlinkt und landet im ICS als URL.
   - **Externe Gäste:** Auswahlfelder (nur bei **normalen** Terminen, nicht bei Fraktion).
   - **Foto** und/oder **Sharepic als Terminbild** (wenn Sharepic für den OV aktiviert ist — siehe unten).
   - **Dateianhänge:** mehrere Dateien, Größe begrenzt (`MAX_UPLOAD_MB` / Anhänge-Limit im Code).

**Kreis / „für alle OVs“:** Wenn ein **Kreis-OV** per Umgebungsvariable `WAHKAMPF_KREIS_OV_SLUG` konfiguriert ist und ihr als **Kreis-Admin** im Kreis-Mandanten arbeitet, erscheint die Option **„In allen Ortsverbänden anzeigen“**. Diese Termine erscheinen dann auch in den anderen OVs (sichtbar wie vom Kreis beworben).

### Teilnahme, Kommentare, Bearbeiten

- Auf der **Terminliste** und der **Detailseite** könnt ihr **zusagen** oder **absagen** (sofern der Termin noch nicht vorbei ist).
- **Kommentare** und die Teilnehmerliste sind pro Termin sichtbar.
- **Bearbeiten/Löschen:** Nur für Ersteller, OV-Admins oder entsprechend berechtigte Konten (grenzüberschreitend für Kreis-Termine nach den Regeln im Code).

---

## Fraktion — Besonderheiten

Die Fraktionsfunktion ist pro OV **deaktivierbar** (Superadmin: Feature **„Fraktion“**). Wenn sie an ist:

### Wer darf was?

- **Fraktionstermine anlegen** dürfen nur **Fraktionsmitglieder** (und Superadmins). Das Flag **„Fraktionsmitglied“** setzt der OV-Admin bei der Mitgliedschaft eines Nutzers.
- Die Oberfläche liegt unter **`/m/<slug>/fraktion/termine`** (Menüpunkt bzw. Tab „Fraktion“ in der Terminübersicht).

### Unterschiede zu normalen Terminen

- Es gibt **keine** Sektion **„Externe Gäste“** bei Fraktionsterminen.
- **Vertraulichkeit:** Beim Anlegen/Bearbeiten könnt ihr **„Vertraulich — nur für Fraktionsmitglieder sichtbar“** aktivieren.
  - **Ohne** diesen Haken sehen **alle freigegebenen Verbandsmitglieder** den Termin.
  - **Mit** Haken sehen nur **Fraktionsmitglieder** (und Superadmin) den Termin — in der Web-UI und in **Kalender-Feeds** (siehe unten: vertrauliche Termine fehlen in öffentlichen Feeds ohne passende Identität).

### Termine aus einem externen Kalender übernehmen („Abonnieren“ Richtung System)

Im **Superadmin** beim jeweiligen Ortsverband:

- Abschnitt **„Kalender-Abo (Fraktionstermine)“**:
  - **Kalender-URL:** öffentlicher **ICS- oder Webcal-Link** (`https://…` oder `webcal://…`). Das eignet sich für veröffentlichte Kalender aus **RIS**, **Stadtratstools** oder **Microsoft 365 / Outlook**, wenn der Kalender **als ICS freigegeben** ist (häufig „Im Internet veröffentlichen“ / Abonnement-Link).
  - **„Kalender-Abo aktiv“:** regelmäßiger Abruf im Hintergrund (Intervall über `CAL_FRAKTION_SYNC_INTERVAL_HOURS` bzw. `CAL_FRAKTION_SYNC_INTERVAL_SECONDS` in `app/config.py`; `0` schaltet den Job ab).
  - Button **„Kalender jetzt abrufen“** zum manuellen Sync.

Neue Einträge aus dem Feed werden als **Fraktionstermine** angelegt (Duplikate werden über einen Import-Schlüssel vermieden). Es werden **keine** bestehenden Termine in der App durch spätere Syncs aktualisiert oder gelöscht — es geht um **das Anlegen fehlender** Ereignisse.

---

## Kalender abonnieren (aus der App heraus)

### Persönliche Feeds (eingeloggt)

Auf der **Terminliste** (und analog in der Termin-Detailansicht) gibt es **„Abonnieren“**. Es werden zwei Feeds angeboten:

| Feed | Inhalt |
|------|--------|
| **Zugesagt** | Termine, für die ihr **zugesagt** habt — über alle OVs, in denen ihr Mitglied seid (plus Kreis-Termine „für alle OVs“ nach derselben Logik wie in der App). |
| **ALLE** | **Alle** Termine in euren freigegebenen Verbänden — mit derselben Filterlogik für **vertrauliche Fraktionstermine** (nur sichtbar, wenn ihr Fraktionsmitglied im jeweiligen OV seid). |

- Links **Apple** nutzen `webcal://…` (Kalender-App).
- **Google** öffnet die Google-Kalender-Einstellung „per URL hinzufügen“.
- **Kopieren** legt die **HTTPS-**ICS-Adresse in die Zwischenablage — für **Microsoft Outlook**, **Outlook im Web** oder **Kalender in Microsoft 365**: dort „Kalender abonnieren“ / „Abonnement von Web“ / „Aus dem Internet“ und die URL einfügen.

Die URLs enthalten einen **geheimen Token** (`t=…`), der eurem Konto zugeordnet ist. **Nicht öffentlich teilen** — wer die URL kennt, sieht den entsprechenden Feed.

### Öffentlicher Mandanten-Feed (ohne Login)

Endpunkt: **`/m/<slug>/calendar.ics?t=<TOKEN>`**

Der Token wird festgelegt über die Umgebungsvariable **`ICS_TOKEN`** (gleicher Token für alle Mandanten über diese Instanz) oder — je nach Betriebskonzept — mandantenspezifisch in der Plattform-DB (technisch vorgesehen in `app/settings_store.py`). Ohne gültigen Token antwortet der Server mit **404**, damit die URL nicht erratbar ist.

Dieser Feed enthält die Termine des Mandanten nach der gleichen **Sichtbarkeitslogik wie öffentlich ohne Nutzerkontext**: **vertrauliche Fraktionstermine** erscheinen **nicht**.

---

## Sharepic-Generator

Menüpunkt **„Sharepic“** (`/m/<slug>/sharepic`), sofern das Feature für den OV **nicht abgeschaltet** ist.

- **Format:** 768×1024 Pixel, mit **SPD-Maske** (Logo, roter Balken, Fußzeile).
- **Foto:** eigenes Bild oder **Hintergrundvorlage** (vom Superadmin pro OV hochladbar, begrenzte Anzahl Vorlagen).
- **Texte:** Slogan (oben rechts), Kurztext im Mittelbalken (Zeichenlimit), Text unten; **OV-Anzeigename** unter dem Schriftzug.
- **Bedienung:** Foto verschieben und zoomen, **Speichern** lädt die Grafik als Datei herunter; **Teilen** nutzt die native Share-Funktion des Browsers, falls verfügbar.

**Standard-Slogan** (z. B. „Für … Für Dich.“) kann der Superadmin pro OV setzen.

### Sharepic direkt im Terminformular

Wenn Sharepic aktiv ist, könnt ihr im Terminformular ein **Sharepic erzeugen und als Terminfoto setzen** (wird vor dem Speichern als JPEG in das Foto-Feld übernommen). Datum/Zeit, Titel und Ort werden aus dem Formular übernommen.

---

## Plakate

Menüpunkt **„Plakate“** (`/m/<slug>/plakate`), sofern aktiviert.

- **Karte** (OpenStreetMap / Leaflet) mit allen **aktuell hängenden** Plakat-Meldungen.
- **Neues Plakat:** Standort durch **Tippen auf die Karte**, **„Neues Plakat am aktuellen Standort“** (wenn der Browser Standortfreigabe hat) oder **„Mein Standort“** zur Orientierung.
- Pro Meldung optional **Notiz** und **Foto** (JPEG/PNG/WebP, Größe begrenzt).
- **„Abhängen“** markiert einen Eintrag als entfernt (für alle sichtbar in der Historie/Logik der App; genaue Darstellung siehe UI).

Superadmins können die Plakat-Daten eines OV bei Bedarf **komplett löschen** (Wartung).

---

## Konfiguration (Auszug)

| Variable | Bedeutung |
|----------|-----------|
| `SECRET_KEY` | Session-Verschlüsselung — in Produktion **stark und geheim** setzen. |
| `SUPERADMIN_USERNAME` / `SUPERADMIN_USERNAMES` | Plattform-Admins für `/admin/…`. |
| `PLATFORM_DATABASE_PATH`, `MANDANTEN_ROOT` | Wo Plattform-DB und OV-Daten liegen (Docker: `/data/…`). |
| `ICS_TOKEN` | Optional: gemeinsamer Token für öffentliche `calendar.ics`-URLs. |
| `MAX_UPLOAD_MB` | Maximale Größe pro Upload (Standard 8). |
| `WAHKAMPF_KREIS_OV_SLUG` | Slug des Kreis-OV für überörtliche Termine. |
| `CAL_FRAKTION_SYNC_INTERVAL_HOURS` | Abstand für automatischen Abruf der Fraktions-ICS-URLs (oder `CAL_FRAKTION_SYNC_INTERVAL_SECONDS`; `0` = aus). |
| `PUBLIC_SITE_HOSTS`, `PUBLIC_SITE_MANDANT_SLUG` | Öffentliche Domain(s) mit festem Mandanten-Slug. |

---

## Hinweis zu „SharePoint“

In diesem Projekt gibt es **keine direkte Microsoft-Graph- oder SharePoint-API-Anbindung**. Stattdessen arbeitet alles **über Standard-ICS**:

- **Hinein in die App:** Im Superadmin die **öffentliche ICS/Webcal-URL** des Kalenders eintragen (z. B. von Outlook/365, wenn der Kalender **zum Abonnieren veröffentlicht** wurde).
- **Heraus in Outlook/365:** Die **kopierte HTTPS-URL** eures persönlichen Feeds („Zugesagt“ / „ALLE“) oder — nach Vereinbarung mit dem Betrieb — `calendar.ics` mit `ICS_TOKEN` als **Abonnement-URL** in Outlook oder im Teamkalender verwenden.

So lassen sich dieselben Inhalte oft auch in **SharePoint-angebundenen** Kalendern nutzen, sofern Microsoft-seitig ein ICS-Abonnement erlaubt ist.

---

## Lizenz / Projekt

Internes Wahlkampf-Projekt — bei Fragen zur Installation oder zu Hosting/Firewall (z. B. ausgehende HTTP-Abrufe für Fraktions-Kalender) den Betrieb der Instanz konsultieren.
