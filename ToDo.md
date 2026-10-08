# ToDo — offene Punkte & Story-Backlog

*Stand 2026-10-08. Erledigt und entfernt: .nfo/.txt-Anreicherung bei fehlendem
Match (umgesetzt mit commit 2faed82) und beets-Abweichungsanalyse
(BEETS-DEVIATION.md, 2026-09-17). Die beiden restlichen Alt-Items sind als
Stories 4.1/4.3 weitergeführt.*

## EPIC 4 — Review-Friktion senken (parallel, unabhängig von MusicGrabber)

- [x] 4.1 Mittleres Band — **abgeschlossen als Analyse 2026-10-08 mit klarem
      Befund**: Die contradiction rule (seit 2026-09-17) deckt den Fall schon
      ab. Offline-Replay der 53 Review-Units mit Kandidaten: **51/53 → asis**,
      2 bleiben korrekt in Review (SCOPE-§5.3-Schutz greift: Dexy's
      different-recording-Veto d=0.055, Style Council Titel-Mismatch d=0.18).
      Zielcheck: eine zusätzliche Mittelband-Regel wäre redundant geworden —
      nicht gebaut. Offen: Re-Decide des Pi-Bestands, sobald erreichbar
      (`musik.py import --status review` + `asis --pending`)
- [x] 4.2 Fetch-Units direkt asis — Tier-3 prüft für `fetch-…`-Units keine
      Ordner-Korroboration mehr (Job-Ordner ist Metadaten, Playlist-Tags pro
      Track autoritativ) → Playlist-Links laufen zur Import-Zeit als asis
      durch, kein Review-Umweg (session.py + smoke_tier3.py + Doku).
      **Offener Live-Test auf dem Pi** (git pull + Bot-Restart, dann Spotify-
      UND YouTube-Playlist-Link schicken): beide müssen ohne Interaktion
      durchlaufen und als Plex-Playlist landen (Testmatrix-Fälle)
- [x] 4.3 Review-Sichtbarkeit — review.csv führt jetzt mit `unit`-
      Identitätsspalte („Artist - Album (N Tracks)") + Kurz-`blocker`,
      `unit_path` bleibt als Apply-Schlüssel hinten (ToDo-Alt-Item #3).
      Nutzer-Check beim nächsten Review offen
- [x] 4.4 Bestandsabbau Windows **erledigt 2026-10-08**: scan retired jetzt
      Review/Unmatched/Network-Units, deren Dateien vollständig weg sind
      (→ `ignored`, reversibel) — Lauf über alle Stale-Roots: 52 Units
      retired, 32 tote Pending-Zeilen gelöscht, 2 echte Review-Fälle
      bleiben bewusst (s. 4.1). **Offen: Pi-Stock gleich prüfen**
      (`musik.py scan --root /mnt/music/_incoming` + `import --status review`)

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
