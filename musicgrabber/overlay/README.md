# Overlay: statische Dateien der gepinnten MusicGrabber-UI (ADR-0001)

Dieses Verzeichnis wird per Bind-Mount
(`./overlay/static:/opt/musicgrabber/static:ro` im docker-compose.yml) über
die statischen Dateien des MG-Containers gelegt (ausgeliefert unter
`/static`). Das Upstream-Backend bleibt unangetastet — hier leben nur die
UI-Dateien, inklusive unseres Import-Monitor-Tabs (EPIC 9, Story 9.4).
Achtung: **seit 4.4.0 wohnt die App in `/opt/musicgrabber`**, vorher
`/app` — bei einem Bump den Mount-Pfad im compose MITPRÜFEN, ein falscher
Pfad lässt den Monitor-Tab STILL verschwinden (UI läuft upstream weiter).

**Basis:** Upstream Image `g33kphr33k/musicgrabber`, Tag **`4.5.3`**
(Code-Repo: GitLab `zarguell/musicgrabber`; Lizenz: Unlicense). Alle 31
statischen Dateien (inkl. `js/` — 12 Dateien, `fonts/`, `images/`,
`theme.js`, `MusicGrabberIcon.webp`) stammen 1:1 aus diesem Image
(Stand 2026-11-13); `.gitattributes` hält sie `-text` — byte-identisch,
keine EOL-Konvertierung, saubere Bump-Diffs. Bump-Lehre 10.1: Dateien
NICHT per Clone-Checkout/`tar` kopieren (autocrlf/MSYS verwandelt LF in
CRLF). **Lehre 11.2:** seit 4.5.1 publiziert das GitLab-Repo keine Tags
mehr (public main = v4.5.0) — Revendor-Quelle ist das DOCKER-IMAGE
selbst (`docker create` + `docker cp <c>:/opt/musicgrabber/static …`,
docker cp ist byte-exakt; auf dem Pi arbeiten, root ownership beachten).

**Unser eigener Diff (Import-Monitor, Story 9.4 + 11.7):** Alle eigenen
Stellen sind mit `musik-monitor:begin` / `musik-monitor:end` (HTML) bzw.
`musik-monitor`-Zeilenkommentaren (JS) markiert:

- `index.html` — 3 Blöcke: Monitor-Button in der Nav (nach Queue),
  `#monitorTabContainer`-Panel (vor `#statsTabContainer`; seit 11.7
  Inhalt = Öffnen-Link statt Datenpanel),
  `<script src="…/static/monitor.js?v=__CACHE_BUST__">` (nach `js/boot.js`)
- `js/core.js` — 3 markierte Stellen (seit 4.4.1, formerly `app.js`):
  `monitorTabContainer`-Konstante (nach `settingsTabContainer`), Eintrag
  in `allTabPanels`, Eintrag in `panelMap`
- `monitor.js` — seit 11.7 ein slim Boot-Script, das nur den Öffnen-Link
  setzt (CSP-grund: siehe unten); die eigentliche Monitor-UI liefert
  der musik-Bot selbst aus: **`http://<pi>:8283/monitor`**
  (`musik/monitor.html`, same-origin — MG 4.4.1+ erzwingt CSP
  `connect-src 'self'` als Backend-Header, womit der frühere
  Cross-Origin-Tab still leer blieb, entdeckt 2026-11-13)

Der Installations-Modul-Check verlangt `overlay/static/index.html`
(70-musicgrabber.sh), probiert `/static/js/core.js` und — entscheidend —
`/static/monitor.js` (gibt es NUR in unserem Overlay; ein falscher
Mount-Pfad fällt damit sofort auf, nicht erst in der UI).

## Bump-Prozedur (Upstream-Update — Testmatrix-Punkt „Overlay-Verträglichkeit")

1. Release Notes des neuen Tags lesen (GitLab-Tags + Docker-Hub-Tags
   gegeneinanderhalten — seit 4.5.1 nur noch Docker Hub!); UI-Diff
   ansehen, z. B. `diff -r <neu>/static overlay/static`.
2. ALLE statischen Dateien aus dem neuen Stand hier hineinkopieren — der
   Mount ersetzt das komplette Verzeichnis; was fehlt, fehlt in der UI
   (`fonts/`, `images/`, `js/` nicht vergessen!). Quelle: das Image
   (docker cp, siehe Lehre 11.2 oben) — byte-exakt, LF.
3. Unsere Monitor-Stellen neu einsetzen (siehe „Unser eigener Diff"
   oben — die Sentinel-Marker im alten Stand zeigen die Stellen; mit
   `git diff HEAD -- overlay/static` isolierbar). Bei Tab-API-Änderungen
   in core.js die 3 Stellen neu lokalisieren
   (`grep -n allTabPanels\|panelMap js/core.js`).
4. Compose-Image-Tag mitziehen, dann
   `docker compose pull && docker compose up -d`.
5. Gegenprüfen: UI lädt, MG-Kernfunktionen (Suche/Queue/Settings)
   arbeiten, Monitor-Tab erscheint und zeigt Daten, `/static/js/core.js`
   und `/static/monitor.js` liefern 200.
