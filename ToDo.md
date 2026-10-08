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

- [x] 1.1 Deployment Pi/Docker — **ausgeführt 2026-10-08 per SSH**:
      docker.io (Debian) + Compose-v2-Plugin-Binary (trixie hat kein
      docker-compose-v2-Paket → PI-SETUP 9.1 entsprechend korrigiert),
      Compose-YAML-Fix (Doppelpunkt im Interpolationsfehlertext),
      Staging `/mnt/music/_incoming/musicgrabber` angelegt, `.env` mit
      generiertem API-Key (PUID 1000), Container Up + HTTP 200, Mounts
      verifiziert (nur Staging + /data). Offen aus 9.5: erster UI-Download
      + ffprobe-Check (Nutzer), Settings-Tab-Feinkonfiguration (= 1.2)
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

## EPIC 6 — Code-Health (Audit 2026-10-08: Totcode/Datentypen/Struktur/Konventionen)

*Audit-Grundlage: 3 Parallel-Recherchen über alle 27 musik/-Module; P1-Befunde
im Code verifiziert. Deploy-Gate: 6.1 + 6.2 + 7.1 müssen vor dem Pi-Deploy
drin sein.*

- [x] 7.1 Story-Workflow-Skill `musik-story-workflow` (Anforderung→Stories→
      fester Ablauf mit Zielcheck+Redundanzcheck; AGENTS.md-Skilliste; dieses
      Backlog) — **Deploy-Gate**
- [x] 6.1 P1-Fixes — **erledigt 2026-10-08**: (a) Override-Apply hängt
      Suchergebnis an `task.candidates` (falscher Kandidat/SKIP-Crash),
      (b) retag `tag_album`-Signatur (Suche aus eigenen Tags statt Pfad),
      (c) `_run_logged` Reader-Thread + Prozessgruppen-/taskkill-T + EIN
      globales Job-Budget über alle Retry-Runden; smoke_decider.py deckt
      Override-Pfad + stummen Timeout-Kill ab
- [x] 6.2 P2-Fixes — **erledigt 2026-10-08**: openable()-Routing (doctor
      dead-rows/Cache/art, report --verify, quality.score, scan stale+
      retirement, session tier3/va_like, asis meta-files, interactive),
      `_album_file_map` TrackInfo-Key („enhanced" wird jetzt gemeldet),
      `_release_kind` chosen.albumtype, gap-fill TimeoutExpired-Handler,
      Singleton-Override-Guard in apply, per-unit-Guard in interactive
      `_run_forced`, plex `_num`-Fallbacks + weitere Exception-Typen;
      smoke_quality.py (Long-Path-Routing)
- [ ] 6.3 Redundanz-Dedup: engine.open_library() (13→1), asis._tag→
      scan.tag_of, state.norm_key/path_under, _cand_id, engine.apply_forced,
      original_year-Fill + MBID-Extraktion entdoubleln, Totcode raus
      (engine._item_paths, jobs.get_job, fetch._OPEN_STATUSES, state.STATUSES→
      wahr+Guard), Privat-Zugriffe public, fetch._unit_label-Rename,
      scan.junk_files privat
- [ ] 6.4 Zyklus session↔asis auflösen (from_fetch/tags_complete → scan,
      enrich_from_meta_files → scan); smoke_tier3 anpassen
- [ ] 6.5 Config/Doku/Installer-Drift: auto_accept_distance-Fallback 0.25,
      scripts/ tracken (pretag_from_folder, va_asis_prepare; beatport_refresh-
      Verweis auf Automatik umstellen), PNGs löschen, --get-playlist-Wortlaut,
      install.ps1 Self-Test + install.sh fpcalc-Label, SCOPE §4.5-Zeile,
      mutagen-Pin
- [ ] 6.6 Tests/CI: manual_tests in CI wiren; smoke_scan.py (Klassifizierung)
      + smoke_decider.py erweitern (Entscheidungsmatrix)
- [ ] 6.7/6.8 später: smoke_gapfill (Temp-Beets-DB für _prepare_units),
      engine↔review/report + fetch↔playlists entflechten, gapfill-Modul,
      beatport-Rename, Decider-Konstanten nach oben, systemd-Template,
      install.ps1 --library, Sprachregel CLI/Bot

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
