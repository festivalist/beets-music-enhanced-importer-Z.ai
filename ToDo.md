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

- [x] 2.1 `musik ingest --root` (Kette aus `fetch --import` ohne
      Download-Teil: scan → prepare → import → asis → cleanup → enrich →
      Plex-Refresh) + systemd-Timer auf dem Pi (15 min, flock) + Telegram-Abschlussbericht —
      **code-fertig 2026-10-08, Deploy/Erstlauf läuft**; MG-Staging gilt
      jetzt als Downloader-Staging (from_fetch erkennt musicgrabber-Pfade,
      per-Track-Albumtags autoritativ); smoke_tier3 Fall 6 deckt das ab
- [ ] 2.2 MG-Playlists-M3U (`Playlists/…` im Staging) in die playlists-Kette
      einspeisen (prepare/build/matching/Plex-Upload, Nachzügler rebuild);
      smoke_playlists um MG-M3U-Fall erweitern
- [ ] 2.3 Duplikat-/Qualitätsgrenzstelle absichern + dokumentieren: MG-Downloads
      vorhandener Alben laufen durch `_prepare_units` (Gap-Fill, _trash mit
      Manifest); MG-Library-Index zeigt NICHT auf die echte Bibliothek.
      Live-Befund 2.5-Probe (Here We Stand): Doppel-Tracknummern im MG-
      Release (Mistress Mabel #6+#17, Look Out Sunshine #4+#18) legten 2
      mindere Duplikate INS Album statt in _trash (manuell geräumt) —
      Gap-Fill sollte Items mit identischem Titel/Tracknr. desselben Albums
      der Qualitätsvergleich unterziehen. Live-Befund 2026-10-10: Cross-
      Engine-Dedup greift bei SINGLETONS nicht (Do Wrong Right als YouTube-
      Fallback-Singleton UND MG-320k-Singleton parallel in der DB, kein
      Trash-Eintrag; manuell geräumt) — Singleton-Neuimport sollte per
      artist+title-Fingerprint gegen vorhandene Singletons verglichen werden
- [x] 2.4 Bot-Routing Freitext → MG-API mit Fallback — **2026-10-08**:
      `musik/musicgrabber.py` (dünner Client: available/search/download/
      wait_for_job; Fehlerklassen MGUnavailable/MGNoResults/MGJobFailed;
      Auswahl-Regel: Artist-Token-Guard gegen Cover-Rang-1, dann MG-Ranking),
      Bot routet Freitext zu MG mit sofortigem ingest nach Download,
      Links unverändert auf spotDL/SomeDL; automatischer Fallback mit
      Grund-Meldung; smoke_musicgrabber.py mit echten API-Fixtures;
      setup.py-Template + PI-SETUP 9.8 (inkl. Crash-Loop-Troubleshooting)
- [x] 2.5 Track-Anfrage → Album-Angebot via MG (Top-3 inkl. neuester) —
      **2026-10-09**: nach Freitext-Track-Import Inline-Buttons mit den
      MB-Kandidaten (releases.track_album_candidates: Recording-Suche →
      Album/EP-RGs, Kompilationen/Live/Singles gefiltert, Cover-Guard,
      neueste RG garantiert, ASCII→Umlaut-Fallback „Eisbaer");
      Tap → MG-Albumpipeline (resolve-release-group → albums/download →
      bulk-import-Status, alles live gegen 4.3.0 verifiziert) → sofortiger
      ingest → Singleton der Track-Anfrage wird entfernt; Teilerfolge
      namentlich gemeldet; kein stiller Lossy-Abstieg (Spotify-Link-
      Hinweis); /status zeigt MG-Live-Zähler; Config album_offer/
      album_job_timeout; smokes: track_album_candidates + album_offer +
      musicgrabber-Albumbfälle; README + PI-SETUP 9.9; Live-Probe: Here
      We Stand 13→18er-Release (Gap-Fill + 3× FLAC-Ersatz), 2 minder-
      qualitative Duplikate als Known-Edge an EPIC 2.3 gemeldet.
      **Nachbesserung (Nutzer-Feedback Bowie „Heroes"):** 5 statt 3
      Vorschläge, Soundtracks gefiltert (2009er OST rangierte über dem
      1977er Album), Jahre per gebündeltem rgid-Lookup nachgereicht
      (Recording-Suche liefert first-release-date kaum) + autoritatives
      Re-Filtern, Ranking Score→Reissue-Gewicht→Jahr aufsteigend
      (Original zuerst; MB-Scores großer Kataloge sind 100-Gleichstände).
      **Zwischenfall 2026-10-10 („/music/Singles" ENOENT):** cleanup
      räumte geleerte MG-Staging-Anker weg → alle MG-Track-Jobs
      scheiterten, Fallback-Imports bekamen kein Album-Angebot; gefixt:
      keep_root schont Top-Level-Ordner, `ensure_staging_layout()` heilt
      vor jedem Download/nach jedem Ingest, Angebot jetzt engine-
      unabhängig (auch im Fallback-Pfad); smoke_cleanup_staging.py neu
- [ ] 2.6 (optional) Album-Angebot auch für Spotify/YouTube-TRACK-Links
      (Kandidatensuche dann aus den importierten Tags) und Freitext-
      Album-Intent („artist - albumname" direkt als Album-Anfrage)

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
- [x] Phase 5b Windows-Bestand übernehmen — **AUSGEFÜHRT 2026-10-09**:
      Windows verify/snapshot (306 Alben/3.864 Items, 0 tote Pfade) →
      tar-over-ssh-Transfer (269 Ordner/4.137 Dateien/39 GB, 0 Fehler;
      SMB-Freigabe wäre ohne Admin nicht skriptbar) → Vollständigkeit exakt
      (nur die 12 bewusst ausgeschlossenen DB-Dateien fehlen) → Trockenlauf
      780 Units/751 would-as-is → Echtlauf 751 importiert, 0 Fehler, 97
      original_years gefüllt → **438 fälschlich als Ein-Track-Alben
      importierte Windows-Singletons zu Singletons konvertiert** und ins
      Singles/-Layout verschoben (34 echte Ein-Track-Alben per Windows-DB-
      Abgleich geschützt) → 29 Units mit unvollständigen Tags bleiben
      unangetastet im Staging (77 Dateien, später review/retry). Endstand:
      **322 Alben / 4.005 Items / 720 Künstler / 38,8 GB, 0 tote Pfade**,
      Plex-Scan, Snapshot, Bot aktiv; doctor --fix (48 Art / 63 Genre)
      nachgelaufen. Pi ist damit die vollständige alleinige Wahrheit;
      Windows-Kopie bleibt eingefrorene Sicherung.
- [x] 5b-Nachlauf Singles-Tree-Regel — **AUSGEFÜHRT 2026-10-09 Abend**:
      Scan erzwingt split_into_singletons für Units unter dem
      konfigurierten Singleton-Root (Root-Name aus dem paths.singleton-
      Template; konsistenter Album-Tag bleibt Album-Einheit) — die 29
      gestrandeten Multi-Single-Ordner (77 Dateien: je Datei Artist/
      Title + wahres Ursprungsalbum, als Album-Unit aber "inkonsistente
      Album-Tags"; should_split feuert bei einem Artist nie) liefen
      29/29 als Singletons, Genres/12 original_years inline gefüllt;
      Staging win-lib leer und entfernt; Endstand **323 Alben /
      4.087 Items / 0 tote Pfade**; smoke_singles_split.py (5 Fälle),
      README-Regel, PI-SETUP 5b nachgezogen.
- [ ] Offene Testfälle aus PI-SETUP Phase 8 (mobiler Netz-Test, 256-kbps-
      ffprobe-Check)
- [ ] SCOPE §8 unverändert: retag --apply, Deezer-Plugin, slskd/Soulseek,
      aktive Bestands-Upgrades

## EPIC 7 — Plex-Konsolidierung: eine Instanz, Musik auf die OMV-HDDs des Ziel-Pis

> **⚠️ VOR START Pflicht-Check (Nutzeranweisung 2026-10-09):** Jüngste
> Entwicklungen aus parallel laufenden Feature-Implementierungen (anderer
> Chat, u. a. bot.py/musicgrabber.py/setup.py/README — Stichwort
> Album-Angebot/Freitext-Alben) einarbeiten und den aktuellen Code-Stand
> prüfen, bevor eine dieser Stories begonnen wird.
> **Start ausschließlich nach explizitem Go des Nutzers.**

Entscheidungen (2026-10-09): Ziel-Pi **192.168.50.43** (SSH wie Pi 5,
Zugang siehe Chat/Memory — nichts Sensibles ins Repo). Darauf laufen der
bestehende TV/Film-Plex sowie **zwei HDDs im Gehäuse, verwaltet über
OpenMediaVault** (SMB nur für andere Geräte; Tool+Plex nutzen lokale
Pfade). Pi 5 wird danach anderweitig genutzt (kein Backup nötig), ABER
vor jedem Eingriff in den Ziel-Plex: **Backup der Plex-Metadatenbank**
(Story 7.0). Beets-DB bleibt lokal auf SD (SQLite niemals auf Netz-
Shares); Musik/_incoming/_playlists/_trash/_backups auf die HDD. Der
TV/Film-Erkennungsfehler verschwindet durch die Konsolidierung selbst
(nach Löschung der Musik-Server-Instanz gibt es genau einen Home-Server).

Vorwissen aus Exploration (Stand a61b489): install.sh ist im Wesentlichen
idempotent (config.yaml bleibt, venv bleibt, Units werden sauber neu
geschrieben, Plex wird nie angefasst, Tokens/State unberührt); Lücken =
Stories 7.1. Hardcodiert: MG-Staging-Mount in docker-compose.yml:32 und
kein first-class Re-Home → Story 7.2.

- [x] 7.0 Sicherungsnetz + Ist-Aufnahme — **AUSGEFÜHRT 2026-10-10**:
      Ziel-PMS-DB-Backup **3,6 GB tar auf HDD2/Rest** (library.db +
      blobs.db + Preferences.xml + LocalAdminToken, aus „Plug-in
      Support/Databases" nach kurzem Stopp). Inventur: ArgonEON, Debian 13
      trixie aarch64, OMV, 2×16,4-TB-btrfs (Musik/Filme/Serien2 auf HDD1,
      Serien/Rest auf HDD2), 238-GB-SSD-Root, Plex 1.43.4, kein Docker.
      ÜBERRASCHUNG: Musik-Share enthielt bereits **581 Alt-Ordner / 108 GB**
      (alte Kollektion, Nutzer-Entscheidung: „Importieren" → neues 7.7).
- [ ] 7.1 Installer-Härtung — **BACKLOG nach der Migration** (nicht
      blockierend; die 4 Lücken aus der Exploration). Teilerfolg direkt
      erledigt: state/-Erst-Lücke in install.sh gefixt (mkdir vor systemd;
      Live-Fall: Ingest-Timer exit 66/NOINPUT auf frischer Box).
- [x] 7.2 — **ENTFALLEN (Redundanzcheck)**: Symlink /mnt/music → HDD-Share
      hält alle Pfade identisch (DB/config/Playlists/compose-Mounts) —
      rehome-Befehl und compose-Env-Gerung werden nicht gebraucht; Symlink-
      Trick in PI-SETUP Phase 10 dokumentiert.
- [x] 7.3 Ziel-Pi vorbereiten — **AUSGEFÜHRT 2026-10-10**: Symlink, Docker
      (docker.io + docker-cli — CLI ist auf trixie nur ein Recommends,
      OMV-apt überspringt es!), Compose-Binary v5.6.0, Clone cdc81a4,
      install.sh „Ready" (config unangetastet), config+cookies+discogs
      kopiert (md5-identisch), Plex-Token der Ziel-Box übernommen, SSH-Key
      Pi-zu-Pi.
- [x] 7.4 Bibliothek transferieren — **AUSGEFÜHRT 2026-10-10**: Pi-5-Dienste
      gestoppt/deaktiviert + MG compose down; rsync 44 GB/31 MB/s (exit 23
      nur Verzeichnis-mtimes); **report --verify: 4.101 Items / 325 Alben /
      0 fehlende Pfade**. Plex-Musik-Section: API-Anlage an PMS 1.43
      gescheitert (location[0] abgelehnt; Scanner heißt „Plex Music");
      Alt-Section-API-DELETE brachte den PMS zum ABSTURZ (Neustart ok,
      TV/Film unversehrt — Backup stand bereit) → **Section-Anlage =
      Nutzer-UI-Schritt**, Playlists folgen nach Scan (offen in 7.6).
- [x] 7.5 Bot + MusicGrabber umziehen — **AUSGEFÜHRT 2026-10-10**: MG-Daten
      (62 MB) übernommen, Container healthy, API 200, min_audio_bitrate
      nachgezogen (fiel auf 128 zurück → wieder 192), Staging durch Symlink
      sichtbar+schreibbar; Pi-5-Bot VORher gestoppt (Single-Poller), Token
      kopiert, Ziel-Bot aktiv (journal sauber), Ingest-Unit läuft.
- [x] 7.6 Abkoppeln + Abnahme — **AUSGEFÜHRT 2026-10-10**: Nutzer-UI
      erledigt (Musik-Section „Musik" auf /mnt/music, key=4; Pi5-Server
      im Konto gelöscht → ein Home-Server). Erster Fullscan: 1.100
      Künstler stabil. CLI-Akzeptanz: YouTube-Download (Cookies aktiv)
      → Import → korrekte Duplikat-Erkennung (Grauzone-Re-Download
      verworfen, bessere Kopie existierte). Playlists: state/playlists/
      nachgezogen, dests aus item_ids regeneriert (zwei Fallstricke:
      veraltete Dateinamen in m3us + Library()-relative-Pfade-Gotcha,
      beide in PI-SETUP Phase 10 dokumentiert) — **alle 5 Playlists
      serverseitig verifiziert** (6/51/11/57/5 Tracks). Plexamp-Endcheck
      beim Nutzer. Nachtrag-Backlog: rebuild --refresh (dests aus
      item_ids neu auflösen als first-class Option) — Kandidat für 7.1.
- [ ] 7.7 NEU (Nutzer-Entscheidung 2026-10-10 „Importieren"): Alt-Kollek-
      tion im Musik-Share (581 Ordner / 108 GB) über musik importieren —
      scan → Trockenlauf → asis-Echtlauf (stundenlang, nohup) → cleanup →
      doctor → Plex-Scan; Überschneidungen mit dem Bestand klären die
      Qualitätstiers; beets organisiert die Dateien nach config-Regeln um.

Reihenfolge: 7.1+7.2 sofort baubar (deploy in 7.3/7.4); 7.0+7.3 live,
dann 7.4→7.5→7.6 an einem Abend. Rollback bis 7.6: Pi 5 unangetastet.

## Beim Nutzer anfragen (bei nächster Gelegenheit)

- Pi: SSH-Zugang/Host bekannt geben für Ferndeployment von Phase 9 — oder
  Bestätigung, dass die Phase selbst ausgeführt wird
- Testdaten für Story 1.3, falls nicht present: Spotify-Playlist-Link,
  YouTube-Playlist-Link, Album-Link, eine 0-day-Release
- Story-2.5-Abnahme über echten Telegram-Bot: 1× Freitext-Track → Album-
  Tap (inkl. ✓-Gap-Fill-Fall) + 1× EP-Kandidat + Verwerfen-Button;
  Idealfall 0-day-Track als „neuester" Kandidat
