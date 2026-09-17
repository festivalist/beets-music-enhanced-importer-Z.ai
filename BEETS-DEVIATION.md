# Wie weit weicht musik vom beets-Standard ab?

Stand: 2026-09-17 · beets 2.13.1 · Analyse der konkreten Abweichungen des
musik-Workflows vom "normalen" beets-Import und -Katalogisierungsstandard,
mit Bewertung (OK / Vorsicht / Abweichung mit Risiko).

## 1. Die großen Abweichungen im Überblick

| # | Thema | beets-Standard | musik | Bewertung |
|---|---|---|---|---|
| 1 | Import-Entscheidung | interaktiver Prompt pro Album (`A`/`U`/`S`/`as-i`) | `ImportSession`-Subklasse entscheidet programmatisch (Decider) | OK — offizieller Erweiterungspunkt von beets, alle Plugins laufen normal |
| 2 | Identitätsprüfung | aggregierte `distance`-Schwelle (`strong_rec_thresh` 0.04) | komponentenweise Prüfung (Albumtitel streng, Artist via Token-Overlap, Track-Mapping, Jahr-Veto, Distanz-Cap 0.25) | OK — behebt bekannte beets-Schwächen (Multi-Artist-Credits, Vinyl-Nummerierung); näher an beets' `medium_rec_thresh` 0.25 |
| 3 | "as-is" | explizite Nutzeraktion am Prompt, selten | Tier-3-Regel: wenn Quellen nichts Verlässliches haben + Tags vollständig + Ordnername stimmt → automatisch asis; seit 2026-09-17 zusätzlich: wenn alle Top-Kandidaten identitätsseitig widersprechen | Vorsicht — bewusstes Risiko des Nutzers ("forgiving, not blind"). Absicherung: nur bei harter Evidenz (Kontradiktion/Leere), nie nach Netzwerkfehlern |
| 4 | VA/DJ-Kompilationen | Artist-Vergleich gegen Release-Credit (scheitert oft) | `va_like`-Units (kein/various Credit, ≥3 Track-Artists) skippen den Artist-Vergleich; Albumtitel-Grenze 0.15 | OK — Nachbildung dessen, was ein Mensch beim Prompt tut |
| 5 | Chart-Dumps | ein "Album" aus N Tracks, falscher Match oder manuell | `should_split` → Singleton-Import pro Track (Kompilations-Erkennung: konsistentes Album-Tag = VA-Album, nie splitten) | OK — beets' Singleton-Modus ist Standard; die automatische Erkennung ist die Erweiterung |
| 6 | Quellen | alle konfigurierten Plugins, immer | `--sources` pro Lauf (Singleton-Pässe ohne Discogs: Release-Ebenen-Datenmüll) | OK — Config bleibt Quelle der Wahrheit, Flag filtert nur |
| 7 | Tag-Schreiben | `write: yes` Standard | `write: yes` | identisch |
| 8 | Datei-Handling | `copy` (Standard) ODER `move` | `move: yes, copy: no` | Vorsicht — Nutzerentscheid (Platz); `_trash` + Manifest kompensiert das fehlende Original |
| 9 | Pfade | `$albumartist/$year - $album` etc. mit `%aunique{}` | `default` mit `%aunique{}`, **`singleton`/`comp` OHNE `%aunique{}`** | ABWEICHUNG MIT RISIKO — Namenskollisionen (gleiches Album zweimal) erzeugen `.1`-Suffixe nur im default-Pfad; in `Compilations\`/`Singles\` kollidieren Pfade still (beets meldet, Pfad wird numeriert, aber DB zeigt alte Pfade). Empfehlung: `%aunique{}` nachrüsten ( kostet nichts, ändert nur Kollisionen ) |
| 10 | `original_year` | MB-Original-Jahr | asis-Imports: `original_year` aus Tag-Jahr nachgefüllt (`_rehome_after_asis`), sonst `0000 -`-Pfade | OK — bekannte asis-Lücke, dokumentiert |
| 11 | Duplikate | `duplicate_action: ask` | Qualitätsvergleich, Verlierer → `_trash` | OK — deterministischer als ask; Konfig `duplicate_action: skip` bleibt als Sicherheitsnetz für manuelle `beet import` |
| 12 | Quiet-Fallback | `skip` | `skip` | identisch |
| 13 | Netzwerkfehler | Plugin-Fehler werden nur geloggt und zählen als "kein Match" | `NetworkErrorRecorder` → Status `network` + automatische Retries | OK — behebt eine echte beets-Schwäche (wichtigste Korrektur überhaupt) |
| 14 | Timeouts | Plugin-abhängig | `socket.setdefaulttimeout(30)` process-weit | OK |
| 15 | Library-Pflege | manuell (`beet`, Export) | `report --verify [--fix]`, `dedupe`, Cleanup-Archivierung, Track-Protokoll, Session-Summary | OK — Monitoring statt Katalogisierungs-Abweichung |

## 2. Verhaltensweisen, die vom beets-Standard abweichen und absichtlich so bleiben

1. **Niemals still übernehmen**: beets' `quiet_fallback: asis` (üblich bei
   Power-Usern) ist bewusst NICHT gesetzt — alles Unsichere geht in die
   Review statt blind mit eigenen Tags in die Bibliothek.
2. **Kompilationen nach Label-Credit**: MOS-Stapel landete teils unter
   `Various Artists\`, teils (asis) unter `Ministry Of Sound\` — der
   beets-Standard würde alles unter den MB-Credit legen. Konsistenz hier
   ist Nutzerwunsch, nicht Bug.
3. **Track-Protokoll je Import** (`[direct]/[enhanced]/[unmapped]`) und
   Session-Summary: existiert in beets nicht.
4. **Beatport4 als Erstquelle für elektronische Singles** — außerhalb des
   beets-Kerns; offizielles Beatport-Plugin ist tot (API v3), der Fork ist
   inoffiziell (Token-Refresh musste selbst gebaut werden).

## 3. Empfehlungen aus der Analyse

- `%aunique{}` in `paths.singleton` und `paths.comp` nachrüsten
  (einzige offen empfohlene Config-Änderung).
- Bei asis-Reihen (`0000 -`-Pfade) fehlen Jahre — zukünftiges `retag`
  (SCOPE §8) kann MB-Jahre nachziehen, sobald Releases indexiert sind.
- Langpfad-Disziplin: Quelldateien ≥260 Zeichen bewegen nicht automatisch
  (beets schweigt) — `fix_stuck_moves.py`-Muster als Werkzeug behalten;
  idealerweise Scan-Warnung bei Unit-Pfaden >240 ausgeben (existiert für
  `openable`, nicht für Move).
