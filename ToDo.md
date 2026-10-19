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
      bleiben bewusst (s. 4.1). Pi-Stock-Check **nachgeholt 2026-10-16** →
      Befunde als 4.5/6.9
- [ ] 4.5 Review-Queue auf dem Pi hat keinen Verbraucher + Contradiction-
      Rule feuert nicht + Multi-Disc-asis-Lücke — **Befund 2026-10-16**:
      drei per drop-here.bat gekommene Greatest-Hits-Alben (Clapton/Tom
      Jones/Judas-Priest-Tribute, 12.10.) lagen 4 Tage in
      `_incoming/windows`. Drei geschichtete Ursachen: (1) Decider setzte
      sie auf `review` („below auto-accept confidence") statt der
      2026-09-17-Policy folgend as-is zu übernehmen — Tom Jones bekam den
      NACHWEISLICH falschen Kandidaten („Gold" 2005 statt GH 2009), das
      Tribute den echten Judas-Priest-Kandidaten, The Coral (1001-#0950)
      sogar „Coldplay" — alles klare Contradiction-Signale; die Regel
      greift offenbar NICHT, wenn schon die Distanz-Schwelle zuschlägt.
      (2) Multi-Disc-Lücke im asis-Pfad: beide 2CD-Rips tragen pro CD
      unterschiedliche Album-Tags („… CD1"/„… CD2") → `tags_complete`
      meldet „inconsistent album tags across files" → asis-Fallback des
      Ingest meldete jeden Zyklus „0 tag-complete unit(s) eligible" und
      auch `asis --unit` griff nicht; Multi-Disc-Units mit per-CD-Tags
      sind im asis-Pfad strukturell nie wählbar. (3) Review-Units haben
      im 15-min-Ingest keinen Verbraucher (import-Filter ignoriert sie).
      **Behoben 2026-10-16 (Betrieb, nicht Code):** Tag-Normalisierung
      pro Unit (Album-Tag vereinheitlicht, discnumber 1/2 gesetzt, Jahr
      aus Ordnernamen) + `asis --unit` Echtlauf als Waiter-Skript
      (Timer stop → Zyklus-Ende abwarten → fix+asis → Plex-Scan → Timer
      an; Log state/asis-fix3.log); Tribute bleibt bewusst in Review
      (Nutzer-Entscheidung 2026-10-16). Stories daraus: (a) Decider-
      Contradiction-Erkennung auch auf Distanz-Review-Fälle anwenden,
      (b) Multi-Disc-Erkennung in `tags_complete` (per-CD-Album-Konsistenz
      + discnumber genügt), (c) Policy-konformer automatischer asis-
      Fallback für eindeutig widersprüchliche Review-Units im Ingest
      (SCOPE-§5.3-Schutzfälle weiter ausgenommen)

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
- [ ] 6.9 IndexError im Pi-Ingest — **Befund 2026-10-16**: Unit „0773.
      G. Love & Special Sauce - G. Love & Special Sauce [1994]" (1001-
      Kollektion, `_incoming/windows`) hängt mit Status `error` und
      „IndexError: list index out of range" (siehe unidentified.csv);
      Ursache ungeklärt — Stacktrace fangen, Unit-Fehlerklasse schärfen
      und den Fall in smoke_scan/smoke_decider abdecken

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
- [x] 7.1 Installer-Härtung — **2026-10-12 aufgegangen in EPIC 8**: die
      Exploration-Lücken (Idempotenz, state/-Erst-Lücke — letztere direkt
      gefixt: mkdir vor systemd, Live-Fall Ingest-Timer exit 66/NOINPUT —,
      fehlende Resume-Fähigkeit, keine OS-Erkennung) werden dort als
      Framework-/Modul-Stories 8.1–8.6 gebaut; rebuild --refresh bleibt
      als separates Playlist-Thema offen (Kandidat EPIC 2-Umfeld).
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
- [x] 7.8 Windows-Ablage (Nutzer-Wunsch 2026-10-10) — **AUSGEFÜHRT**:
      ingest-Roots konfigurierbar (`musik: ingest: roots`, Default =
      MG-Staging nur → bestehende Setups unverändert; Smoke
      smoke_ingest_roots.py, 5 Fälle, alle 11 Smokes grün);
      drop-here.bat (robocopy-Kopie auf `\<pi>\Musik\_incoming\windows`,
      Multi-Drop, Namenskollisionen mit -2-Suffix, MUSIK_DROP-Override,
      Share-Probe vor dem ersten Kopieren); README „Windows-PC → Pi
      library" + Dateitabelle, PI-SETUP Phase 10; Deploy auf Ziel-Pi
      (config-Roots + Dropzone) im selben Zug.
- [ ] 7.7 NEU (Nutzer-Entscheidung 2026-10-10 „Importieren"): Alt-Kollek-
      tion im Musik-Share (581 Ordner / 108 GB) über musik importieren —
      scan → Trockenlauf → asis-Echtlauf (stundenlang, nohup) → cleanup →
      doctor → Plex-Scan; Überschneidungen mit dem Bestand klären die
      Qualitätstiers; beets organisiert die Dateien nach config-Regeln um.

Reihenfolge: 7.1+7.2 sofort baubar (deploy in 7.3/7.4); 7.0+7.3 live,
dann 7.4→7.5→7.6 an einem Abend. Rollback bis 7.6: Pi 5 unangetastet.

## EPIC 8 — Portabler One-Shot-Installer (Plan genehmigt 2026-10-12)

> Nutzerentscheidungen (2026-10-12): **beide Pfade gleichwertig** — OMV nur
> auf Debian/Raspberry Pi OS, Ubuntu bekommt den ohne-OMV-Pfad (fstab +
> Samba mit force user, kein Hack für OMV-auf-Ubuntu); **Plex nativ** per
> Paket (apt-Repo, trixie-SHA1 → auto Plan B direktes .deb); **Tests in
> QEMU-VMs** auf dem Windows-PC. Der laufende Pi (192.168.50.43) bleibt
> unangetastet — kein Installer-Code gegen ihn, er sieht den Epic nur per
> git pull; install.sh bleibt über `--core-only` abwärtskompatibel.
> Architektur: modularer Treiber + install.d/-Module, State/Resume unter
> /var/lib/musik-installer, Destruktiv-Guards, --dry-run/--answers/
> --non-interactive, offene Modul-Registry für spätere Tandoor/Immich-
> Stories. Nicht-Ziele: Datenmigration Pi→Dell (später eigene Story),
> Plex als Docker, OMV auf Ubuntu erzwingen.

- [x] 8.1 Installer-Framework — **2026-10-12**: install.sh = modularer
      Treiber (Module als eigene Prozesse: 0=ok/77=skip/78=fail; Pflicht-
      modul-Fail stoppt mit Resume-Hinweis, Optionalmodul-Fail fragt/
      läuft weiter), install.d/lib/common.sh (State %q-atomar, Prompts
      never-ask-twice, menu/confirm, run()=Dry-Run-fähig, sudocmd),
      Module 00-detect (OS/Arch-Matrix, OMV nur Debian-Familie, RAM/Platz-
      Warnung, sauberer Abbruch auf Nicht-Linux VOR jeder Änderung),
      10-base (Grundpakete, fpcalc-Label-Drift aus 6.5 korrigiert),
      60-musik (bisheriger install.sh-Kern, Verhalten unverändert,
      --library/--no-systemd weiter gültig); CLI: --core-only/--only/
      --list/--fresh/--resume/--add-disk/--dry-run/--answers/--non-
      interactive; Treiber-Logiktests unter Git Bash: Pflichtfail-Stop,
      Resume-Skip, Optionalfail-Weiterlauf, Dry-Run ohne MOD-Persistenz
      (Laufzeit-Statustabelle gefixt), Answers-Parser zeilenweise (kein
      source), Prompt-Rückgabe stderr-getrennt; .gitattributes pinnt *.sh
      auf LF (autocrlf=true hätte CRLF-Checkouts produziert); subsummiert
      7.1. **Offen bis 8.7:** QEMU-Matrix gegen echte Debian/Ubuntu-VMs
- [x] 8.2 Platten-Modul — **2026-10-12**: install.d/20-disks.sh — Kandidaten
      nur ganze, NICHT eingehängte Datenplatten (Root-Platte fällt unter
      dieselbe Regel), Identitätsanzeige (Modell/Serie/Größe/alter Typ/
      Partitionen) vor Formatierung, Bestätigung nur durch Eintippen von
      JA — bewusst NICHT State-speicherbar (confirm_destructive; nicht-
      interaktiv nur mit --force), wipefs+mkfs btrfs (single/raid1,
      1–2 Platten) oder ext4, fstab per UUID+nofail mit Backup+mount -a-
      Probe+Rollback, Idempotenz (bereits gemountet/OMV-Symlink → ok ohne
      Format), OMV-Bestandserkennung → nur /mnt/music-Symlink auf den
      Share (+Schreibprobe, force-user-Hinweis), Strategie-Menü fstab|
      OMV|ohne Platte; --add-disk: separater Mount oder btrfs device add
      (Balance nur als Hinweis — Stunden auf Multi-TB); Mock-Harness
      manual_tests/harness_disks.sh (6 Szenarien, 23 Assertionen, läuft
      auch Git Bash): fstab-Lauf, Idempotenz, OMV-Skip, beide Add-Disk-
      Wege, destruktiv-ohne--force → alles grün; INSTALLER_MUSIC_MOUNT/
      INSTALLER_FSTAB als dokumentierte Harness-Overrides
- [x] 8.3 OMV- + Samba-Modul — **2026-10-12**: 30-omv — nur bei
      ANSWER_omv_supported=1 (Ubuntu → ehrlicher Skip mit Pfad-Verweis);
      Bestands-OMV (ArgonEON) → nichts ändern, Integrations-Checkliste
      (force user, smbmd-Probe, --only disks nach Share-Anlage); frische
      Installation über das offizielle omv-extras-InstallScript mit
      Vorab-Warnung (10–20 min, apt-Übernahme, SSH-HÄRTUNG — Key-Login
      sichern!), Install-Entscheidung durch disks_mode=omv vorbefriedigt
      oder explizites Menü; 32-samba — skippt bei OMV, braucht
      Musik-Root (ANSWER_library), samba apt + idempotenter Share-Block
      „Musik“ (Marker) mit force user + guest ok (drop-here.bat-Parität,
      Live-Lektion Phase 10), map to guest per sed in den BESTEHENDEN
      [global]-Block (kein Dublett-Abschnitt — testparm duldet das nicht),
      smbd enable+Probe Port 445, kein Port-Forwarding-Hinweis;
      finish(skip) gibt Meldung jetzt auch auf Konsole (stderr);
      Harness manual_tests/harness_samba.sh: 9/9 grün (Share-Anlage,
      Idempotenz byte-identisch, OMV-Rückzug, Ubuntu-Skip), disks-
      Harness 23/23 unverändert
- [x] 8.4 Docker- + Plex-Modul — **2026-10-12**: 40-docker — Distribution-
      pakete (docker.io + docker-cli explizit: trixie-Recommends-Falle aus
      7.3), Compose-v2-Standalone-Binary arch-bewusst (aarch64/x86_64 statt
      hartkodiertem aarch64 aus 9.1), Dienst-Probe, Run-User in docker-
      Gruppe mit Neu-Anmelde-Hinweis, Menü ja/nein; 50-plex — nativer
      apt-Repo-Weg mit automatischer SHA1/sqv-Erkennung → Plan B (Repo
      .disabled + neuestes .deb arch+distro-bewusst von plex.tv-API),
      danach Assistenz: Claim-URL, PlexOnlineToken aus Preferences.xml,
      plex-Block-Setter für config.yaml per Inline-Python (ersetzt
      kommentierte Platzhalter ODER fügt unter musik: ein, Backup vorher;
      ohne config.yaml → --only plex später), Berechtigungs- und Remote-
      Access-Hinweise; finish(ok) meldet jetzt auch auf Konsole;
      hostname -I unter pipefail robust (Git-Bash-Live-Fund); Harness
      manual_tests/harness_dockerplex.sh 17/17 (Frischinstall, Idempotenz,
      Claim-Pfade, Setter mit kommentierten Platzhaltern UND ohne
      plex-Block — echtes venv-Python), Regression disks 23/23 +
      samba 9/9
- [x] 8.5 musik-Modul polished + MusicGrabber-Modul — **2026-10-12**:
      60-musik per Kommentar-Diff gegen den alten install.sh-Kern
      verifiziert (nur intendierte Rahmen-Änderungen: run/sudocmd/have,
      finish-with-Resume-Hinweis, Dry-Run-Guards; systemd-Units und
      venv-Gate waren Dry-Run-undicht — gefixt); 70-musicgrabber —
      Staging-Anker host-seitig als Run-User (Crash-Loop-Lehre 9.8),
      .env aus Example mit PUID/PGID (KEIN API-Key — UI-Lockout-Lektion),
      compose up nur wenn Container nicht läuft (2,6-GB-Pull),
      HTTP-Probe mit Geduld (INSTALLER_MG_WAIT, Default 600 s),
      ohne Musik-Root sauberer Skip; install.ps1 Self-Test nachgerüstet
      (6.5-Drift, Parität zu install.sh) + README-Satz, PI-SETUP-Statusnote;
      Harness manual_tests/harness_mg.sh 9/9, Regression: disks 23/23,
      samba 9/9, dockerplex 17/17
- [x] 8.6 Verify-Modul — **2026-10-12**: 90-verify tastet jede Komponente
      REAL ab (nicht dem State glauben): Musik-Root (Mount/Symlink/Ordner +
      Schreibprobe als Run-User), musik-Tool (venv+config) + Erinnerungen
      für fehlende Tokens/Cookies/Allowlist, systemd-Units (enabled/aktiv),
      Docker (docker info) + MG (Container + Web-UI-Probe), Plex (API
      :32400/identity + Claim-Check), SMB (OMV-Zweig vs. samba-Share +
      Dropzone-Pfad), OMV-Hinweis nur wenn Musik-Root nicht verdrahtet;
      sammelt „manuell offen“-Liste (bewusste UI-/Einmal-Schritte) statt
      zu failen — Modul ist reine Diagnose; doctor-Empfehlung mit
      --limit 50 (Erstlauf ohne Limit = Stunden, PI-SETUP-Warnung);
      Harness manual_tests/harness_verify.sh 13/13 (Voll-Host und leerer
      Host)
- [x] 8.7 QEMU-Testmatrix + Doku — **2026-10-12**: VM-Harburg auf dem
      Windows-PC aufgebaut (scoop-QEMU ohne Admin, da choco/UAC scheiterte;
      Debian-12- + Ubuntu-24.04-Cloud-Images, Cloud-init-NoCloud per
      SMBIOS+HTTP-Seed, virtuelle 8-GB-Datenplatten als echte
      mkfs/mount/fstab-Kandidaten; WSL2-Komponenten wurden versehentlich
      mitinstalliert — brauchen Neustart, ungenutzt gelassen).
      manual_tests/qemu_matrix.sh (setup/boot/run/stop) dokumentiert die
      Prozedur inkl. der beiden VM-Wartfälle (Cloud-Root 3–3,5 GB zu klein
      für Docker+Plex+venv → Resize+growpart; dpkg-interrupt nach Voll-Disk).
      **Matrix-Ergebnisse echt grün:** Debian 12: detect, disks (btrfs auf
      vdb, fstab verifiziert), base+musik (Self-Test, Units enabled),
      Resume-Idempotenz (3 Skips), --add-disk (vdc → /mnt/disk2 inkl.
      fstab), docker (Compose v5.6.0 amd64 + hello-world-Container-Run),
      plex (Repo-Weg, Dienst aktiv, Claim-Ausstieg sauber), samba (testparm
      bestätigt force user/guest ok), verify (Report-Karte trifft den
      Ist-Zustand exakt, 5 manuelle Schritte). Ubuntu 24.04: detect mit
      OMV-Ablehnung, disks btrfs, base+musik (Self-Test, Units), docker,
      verify. **7 echte Modul-Bugs fand und fixte die Matrix** (btrfs-progs
      fehlt, blkid ohne sudo-PATH, Deno-Pfad ~/.config/spotdl + unzip,
      --add-disk vom Resume-Skip verschluckt, fstab-Doppelcheck auf falsche
      Variable, docker-cli-Paket nur trixie, gpg ohne --yes, dpkg-Lock-
      Retry) — Commit-Kette c180591…; Mock-Harnesses 71+ Assertionen
      grün gehalten. **Bewusst NICHT in der VM:** OMV-Installation (10–20 min
      InstallScript, übernimmt die VM — Erst-Test auf dem Dell-Tag geplant;
      Ubuntu-Ablehnung + Bestands-OMV-Integration sind gedeckt), MG-
      Container-Deploy (2,6-GB-Pull; Logik im Mock-Harness). Doku:
      PI-SETUP Phase 1+2 zum One-Shot-Kapitel verschmolzen (Modultabelle,
      Robustheit, manuelle Varianten), 5.1/9.1 Installer-Verweise, README
      (Linux-Absatz + Dateitabelle). Offen vom Epic: nichts — Dell-Tag:
      OMV-Modul erstmalig real, 7.7 Alt-Import, 8.8-Migrationsstory

## EPIC 9 — Import-Monitor (Grilling 2026-10-19; Scope-Change in SCOPE §2 dokumentiert)

Sichtbarkeit der Automatisierung ohne SSH: Web-Tab in der MusicGrabber-UI
zeigt Laufstatus, Unit-Status, Review-Queue und `_incoming`-Stau; Aktionen
laufen über den Bot-Executor. Schließt die Sichtbarkeitslücke aus 4.5(3)
(Review-Units lagen tagelang unbemerkt). Entscheidungen 2026-10-19:
Overlay-Fork auf gepinntem MG-Image 4.3.1 (ADR-0001), Aktionen nur über
Bot-HTTP-Endpoint mit ingest.lock (ADR-0002), LAN-only ohne Login (gleiche
Betriebsart wie MG), kanonischer Begriff „Import-Monitor“ (GLOSSARY.md).

- [ ] 9.1 Bot-HTTP-Endpoint (Executor-API) — bot.py bekommt LAN-Endpoint
      (Bind nur LAN-Interface, keine Auth wie MG-UI): GET-Snapshot
      (Job-Queue + state.json-Counts + Units je Status + Review-Liste +
      `_incoming`-Stau) und POST-Aktionen (enqueue in die bestehende
      Job-Queue: review-apply, retry, asis, ingest-trigger). Wiederverwendet
      `_run_exclusive`/jobs vollständig, keine neue Executor-Logik. Test:
      Smoke gegen seeded state.json; Abnahme auf dem Pi mit echtem Ingest.
      — **Code erledigt 2026-10-19** (`musik/bot_http.py` + Job-Kinds
      retry/ingest im Bot; chat_id 0 = kein Telegram-Push; Smoke
      manual_tests/smoke_bot_http.py inkl. HTTP-Roundtrip grün; Port
      8283, config `musik: bot_http: {enabled, host, port}`). **Offen:
      Abnahme auf dem Pi** (endpoint live gegen echten Ingest) —
      review-apply als Aktion bewusst auf 9.5 verschoben
      (apply_decisions ist CSV-zentriert, bekommt mit dem Web-Tab seine
      per-Unit-API)
- [ ] 9.2 `/status`-Erweiterung — Telegram-Kurzüberblick (Nutzer-Wunsch
      „ganz kurz“): eine Zeile Timer-Ingest-Stand aus state.json (Counts +
      letzte Änderung + „läuft gerade“ via ingest.lock-Probe; Windows-Dev
      ohne fcntl → „unbekannt“) + Review-Stau-Zeile. Freistehend,
      kleinster Tracer. Test: seeded state.json; echte `/status` auf dem
      Pi beim nächsten Bot-Deploy. — **Code + Smoke
      (manual_tests/smoke_status_state.py) erledigt 2026-10-19; offen:
      /status-Echtprüfung auf dem Pi beim nächsten Deploy**
- [ ] 9.3 Overlay-Deployment — docker-compose pinnt
      `g33kphr33k/musicgrabber:4.3.1` (statt latest) + Bind-Mount
      `musicgrabber/overlay/static` → MG-static (Tab-Dateien aus diesem
      Repo, Upstream-Backend unangetastet); install.d-Modul + PI-SETUP.md
      same-commit; Testmatrix-Punkt „Overlay-Verträglichkeit bei Bump“.
      Blockiert: — — **erledigt 2026-10-19 (Repo-Seite)**: Pin + ro-Mount
      im Compose, alle 6 static-Dateien von Tag v4.3.1 vendored
      (`.gitattributes -text`), Bump-Prozedur in overlay/README.md,
      Modul prüft Overlay + `/static/app.js` (Harness 11/11), PI-SETUP
      9.3b + Update-Zeile. **Offen: Rollout auf dem Pi** (git pull +
      compose up — beim nächsten Pi-Tag mit 9.1/9.2-Abnahme)
- [ ] 9.4 Web-Tab „Import-Monitor“ (Anzeige) — Vanilla-JS-Tab in
      `musicgrabber/overlay/static`: Laufstatus (a), Statuszahlen +
      filterbare Unit-Liste (b), Review-Queue (c), `_incoming`-Stau (d);
      Poll ~5 s gegen den 9.1-Endpoint. Blockiert von 9.1, 9.3. Test:
      Browser-Check gegen Mock-Endpoint + Pi. — **erledigt 2026-10-19
      (Code + Mock-Abnahme)**: `monitor.js` (standalone, eigenes CSS,
      XSS-escaping, 5-s-Poll mit Visibility-Pause), 3 markierte Blöcke in
      index.html + 3 Zeilen in app.js (Sentinel `musik-monitor`), CORS +
      OPTIONS-Preflight im Endpoint. Browser-Check gegen echte
      bot_http-Instanz mit Test-Daten grün: Tab rendert (Kopf, Review-
      Box, Jobs, Chips-Filter, Tabelle), Filter-State über Tab-Wechsel
      stabil, Upstream-Tags unbeschädigt, Dark-Theme-Passung im
      Screenshot geprüft. **Offen: Pi-Abnahme** (echte Daten, Hell/Dunkel-
      Theme, Poll über mehrere Minuten gegen echten Ingest)
- [ ] 9.5 Aktionen im Tab — Review annehmen/override, Retry, asis,
      Ingest-Trigger als Buttons → POST auf 9.1; Bestätigungsstufe für
      bibliotheksschreibende Aktionen; Fortschritt aus der Job-Queue.
      Blockiert von 9.4. Test: je Aktionstyp ein Echtlauf auf dem Pi.
      — **Code erledigt 2026-10-19**: `review.apply_decisions_rows()`
      (CSV-freier Kern, apply_decisions delegiert nur noch), Bot-Job-Kind
      `review` (apply unter ingest.lock), Endpoint-Aktion `review`
      (Vokabular accept/accept2/override/unmatched/ignore, Pre-Validierung
      gegen Status+Pfad), Snapshot-Review trägt jetzt Kandidaten-Labels;
      Tab-Buttons K1/K2/As-is/Override/Ignorieren je Review-Unit + global
      „Ingest jetzt“/„Netz-Retry“, Bestätigungsdialoge, Erfolgsmeldung
      überlebt Poll-Re-Renders. Smoke smoke_review_apply_rows.py (gemockter
      Engine-Layer: accept/accept2 forcieren die richtigen Kandidaten-IDs,
      Abfänger-Zweige, CSV/Report-Refresh) + erweiterter smoke_bot_http
      grün; Browser-Abnahme gegen echte bot_http-Instanz: K1/K2/Ignore/
      Ingest-Trigger mit confirm-Dialog, Queue-Zähler wächst, Screenshot
      ok. **Offen: Pi-Echtläufe** (je Aktionstyp 1× gegen echte Daten)

Bewusst später (eigene Story, kein Teil dieses EPICs): generelles
Versions-Pinning für alle Import-Abhängigkeiten (Nutzer-Strategie
2026-10-19).

## Beim Nutzer anfragen (bei nächster Gelegenheit)

- Pi: SSH-Zugang/Host bekannt geben für Ferndeployment von Phase 9 — oder
  Bestätigung, dass die Phase selbst ausgeführt wird
- Testdaten für Story 1.3, falls nicht present: Spotify-Playlist-Link,
  YouTube-Playlist-Link, Album-Link, eine 0-day-Release
- Story-2.5-Abnahme über echten Telegram-Bot: 1× Freitext-Track → Album-
  Tap (inkl. ✓-Gap-Fill-Fall) + 1× EP-Kandidat + Verwerfen-Button;
  Idealfall 0-day-Track als „neuester" Kandidat
