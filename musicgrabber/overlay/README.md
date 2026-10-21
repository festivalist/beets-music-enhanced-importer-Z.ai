# Overlay: statische Dateien der gepinnten MusicGrabber-UI (ADR-0001)

Dieses Verzeichnis wird per Bind-Mount
(`./overlay/static:/opt/musicgrabber/static:ro` im docker-compose.yml) über
die statischen Dateien des MG-Containers gelegt (ausgeliefert unter
`/static`). Das Upstream-Backend bleibt unangetastet — hier leben nur die
UI-Dateien, inklusive unseres Import-Monitor-Tabs (EPIC 9, Story 9.4).
Achtung: **seit 4.4.0 wohnt die App in `/opt/musicgrabber`**, vorher
`/app` — bei einem Bump den Mount-Pfad im compose MITPRÜFEN, ein falscher
Pfad lässt den Monitor-Tab STILL verschwinden (UI läuft upstream weiter).

**Basis:** Upstream `g33kphr33k/musicgrabber`, Tag **`v4.4.0`** (Lizenz:
The Unlicense). Alle 16 statischen Dateien (inkl. `fonts/`, `images/`,
`MusicGrabberIcon.webp`) stammen 1:1 von diesem Tag (Stand 2026-10-21);
`.gitattributes` hält sie `-text` — byte-identisch, keine
EOL-Konvertierung, saubere Bump-Diffs. Bump-Lehre 10.1: Dateien NICHT per
Clone-Checkout/`tar` kopieren (autocrlf/MSYS verwandelt LF in CRLF), sondern
als Blobs: `git -C <clone> show v4.4.0:static/<datei> > <ziel>` oder
`git archive … | tar -x` (Blob-Bytes, keine Wandlung).

**Unser eigener Diff (Import-Monitor-Tab, Story 9.4):** Alle eigenen
Stellen sind mit `musik-monitor:begin` / `musik-monitor:end` (HTML) bzw.
`musik-monitor`-Zeilenkommentaren (JS) markiert:

- `index.html` — 3 Blöcke: Monitor-Button in der Nav, `#monitorTabContainer`-
  Panel, `<script src="…/static/monitor.js?v=__CACHE_BUST__">`
- `app.js` — 3 markierte Zeilen: `monitorTabContainer`-Konstante, Eintrag
  in `allTabPanels`, Eintrag in `panelMap`
- `monitor.js` — komplett ours (standalone, kein Upstream-Code)

Der Installations-Modul-Check verlangt `overlay/static/index.html`
(70-musicgrabber.sh), probiert `/static/app.js` und — entscheidend —
`/static/monitor.js` (gibt es NUR in unserem Overlay; ein falscher
Mount-Pfad fällt damit sofort auf, nicht erst in der UI).

## Bump-Prozedur (Upstream-Update — Testmatrix-Punkt „Overlay-Verträglichkeit")

1. Release Notes des neuen Tags lesen; UI-Diff ansehen, z. B.
   `git diff --no-index --ignore-cr-at-eol overlay/static/app.js <neu>/app.js`
2. ALLE statischen Dateien aus dem neuen Tag hier hineinkopieren — der
   Mount ersetzt das komplette Verzeichnis; was fehlt, fehlt in der UI
   (`fonts/` und `images/` nicht vergessen!).
3. Unsere Monitor-Stellen neu einsetzen (siehe „Unser eigener Diff"
   oben — die Sentinel-Marker im alten Stand zeigen die Stellen; mit
   `git diff voriger-Tag..HEAD -- overlay/static` isolierbar).
4. Compose-Image-Tag mitziehen, dann
   `docker compose pull && docker compose up -d`.
5. Gegenprüfen: UI lädt, MG-Kernfunktionen (Suche/Queue/Settings)
   arbeiten, Monitor-Tab erscheint und zeigt Daten, `/static/app.js`
   liefert 200.
