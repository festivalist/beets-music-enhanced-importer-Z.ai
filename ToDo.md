# ToDo — offene Punkte & Story-Backlog

*Stand 2026-10-08. Erledigt und entfernt: .nfo/.txt-Anreicherung bei fehlendem
Match (umgesetzt mit commit 2faed82) und beets-Abweichungsanalyse
(BEETS-DEVIATION.md, 2026-09-17). Die beiden restlichen Alt-Items sind als
Stories 4.1/4.3 weitergeführt.*

## EPIC 4 — Review-Friktion senken (parallel, unabhängig von MusicGrabber)

- [ ] 4.1 Mittleres Band (0.25–0.35) entschärfen: auto-asis, wenn kein
      Top-Kandidat die Identitäts-Gates besteht und tags_complete + Ordner-/Tag-
      Übereinstimmung vorliegt — generalisierte Regel in `musik/session.py`,
      kein Einzelfall-Tuning; vorher/nachher-Zähler per dry-run (ehem. ToDo #1)
- [ ] 4.2 `from_fetch`-Units mit complete tags direkt asis führen — Playlist-
      Links sollen nicht mehr systematisch im Review landen; PI-SETUP-
      Formulierung „das ist normal" entfernen
- [ ] 4.3 Review-Sichtbarkeit: betroffener Track/Album prominent (erste
      Spalte/Kopfzeile) in review.csv, `musik review`, session-report (ehem.
      ToDo #3)
- [ ] 4.4 Bestandsabbau: offene Units (Stand Windows-Kopie 2026-10-08: 88 =
      53 review + 32 pending + 2 review-apply + 1 unmatched; auf dem Pi
      nachzählen) einmalig decided — nach 4.1 per dry-run, Rest `/asis ALLE`
      bzw. review.csv-apply; Baseline dokumentieren, Ziel dauerhaft ≈ 0

## EPIC 1 — MusicGrabber auf dem Pi (Beschaffungs-Engine Nr. 2)

- [ ] 1.1 Deployment Pi/Docker — arm64 bestätigt (Docker-Hub-Tags multi-arch),
      `musicgrabber/docker-compose.yml` + PI-SETUP Phase 9 stehen bereit;
      ausstehend: Ausführung auf dem Pi (Docker installieren, `.env`, Start,
      Staging-Verzeichnis, Berechtigungen)
- [ ] 1.2 Quellen & Qualität konfigurieren: Monochrome (FLAC) + YouTube +
      SoundCloud + FreeMp3Cloud aktiv, MIN_AUDIO_BITRATE an lossless-first
      anpassen, YouTube-Cookies hinterlegen; Telegram-Notify nur mit separatem
      Bot-Token (Polling/Webhook-Konflikt mit musik-bot) — sonst verzichten
- [ ] 1.3 Abnahme gegen Testmatrix (musik-testdaten): Single-Suche, Album-Link,
      Spotify-Playlist-Link, YouTube-Playlist-Link, 0-day ohne MB-Eintrag —
      jeweils: landet im Staging, Tagging-Qualität, ffprobe-Bitrate; Ergebnis
      protokollieren

## EPIC 2 — Ingest-Kette MG-Staging → beets → Plexamp

- [ ] 2.1 `musik ingest --root <staging>` (Kette aus `fetch --import` ohne
      Download-Teil: scan → prepare → import → asis → cleanup → enrich →
      Plex-Refresh) + systemd-Timer auf dem Pi + Telegram-Abschlussbericht;
      scan-Klassifizierung des MG-Layouts (Singles/Artist/Title) verifizieren
- [ ] 2.2 MG-Playlists-M3U (`Playlists/…` im Staging) in die playlists-Kette
      einspeisen (prepare/build/matching/Plex-Upload, Nachzügler rebuild);
      smoke_playlists um MG-M3U-Fall erweitern
- [ ] 2.3 Duplikat-/Qualitätsgrenzstelle absichern + dokumentieren: MG-Downloads
      vorhandener Alben laufen durch `_prepare_units` (Gap-Fill, _trash mit
      Manifest); MG-Library-Index zeigt NICHT auf die echte Bibliothek
- [ ] 2.4 Bot-Routing Freitext → MG-API (search → download → Job-Poll) mit
      Fallback auf spotDL/SomeDL; `/status` zeigt MG-Jobs (optional, nach 2.1–2.3)

## EPIC 3 — Beschaffung ohne Nutzerinteraktion

- [ ] 3.1 Watched Playlists in MG (Spotify/YouTube; Append für wachsende,
      Mirror für kuratierte Listen; Intervalle; Cookie für private Listen)
- [ ] 3.2 Artist-Watch: MB-Artist-Follow für Kernkünstler (Kandidaten aus
      `musik stats`), from-date = Einrichtungsdatum (kein Retro-Download);
      Rollentrennung dokumentieren (MG handelt, `musik releases` bleibt Report)
- [ ] 3.3 Track-Upgrades lossy→lossless report-first (optional; Apply bleibt
      manuelle Ausnahme, SCOPE §8)

## EPIC 5 + Späteres

- [ ] 5.1 Routing umstellen (MG primär, spotDL/SomeDL Fallback) + README-
      YouTube-Breakage-Runbook straffen — erst nach abgeschlossenem EPIC 3
- [ ] Offene Testfälle aus PI-SETUP Phase 8 (mobiler Netz-Test, 256-kbps-
      ffprobe-Check)
- [ ] SCOPE §8 unverändert: retag --apply, Deezer-Plugin, slskd/Soulseek,
      aktive Bestands-Upgrades

## Beim Nutzer anfragen (bei nächster Gelegenheit)

- Pi: SSH-Zugang/Host bekannt geben für Ferndeployment von Phase 9 — oder
  Bestätigung, dass die Phase selbst ausgeführt wird
- Testdaten für Story 1.3, falls nicht present: Spotify-Playlist-Link,
  YouTube-Playlist-Link, Album-Link, eine 0-day-Release
