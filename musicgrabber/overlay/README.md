# Overlay: statische Dateien der gepinnten MusicGrabber-UI (ADR-0001)

Dieses Verzeichnis wird per Bind-Mount (`./overlay/static:/app/static:ro`
im docker-compose.yml) über die statischen Dateien des MG-Containers
gelegt (`/app/static`, ausgeliefert unter `/static`). Das Upstream-Backend
bleibt unangetastet — hier leben nur die UI-Dateien, inklusive unseres
Import-Monitor-Tabs (EPIC 9, Story 9.4).

**Basis:** Upstream `g33kphr33k/musicgrabber`, Tag **`v4.3.1`** (Lizenz:
The Unlicense). `app.js`, `index.html`, `release-notes.js`, `style.css`,
`quips.js`, `favicon.png` sind 1:1-Kopien davon (Stand 2026-10-19);
`.gitattributes` hält sie `-text` — byte-identisch zum Tag, keine
EOL-Konvertierung, saubere Bump-Diffs.

Der Installations-Modul-Check verlangt `overlay/static/index.html`
(70-musicgrabber.sh) und probiert `/static/app.js` — ein leeres oder
fehlerhaftes Overlay fällt also sofort auf, nicht erst in der UI.

## Bump-Prozedur (Upstream-Update — Testmatrix-Punkt „Overlay-Verträglichkeit")

1. Release Notes des neuen Tags lesen; UI-Diff ansehen, z. B.
   `git diff --no-index --ignore-cr-at-eol overlay/static/app.js <neu>/app.js`
2. ALLE sechs Dateien aus dem neuen Tag hier hineinkopieren — der Mount
   ersetzt das komplette Verzeichnis; was fehlt, fehlt in der UI.
3. Import-Monitor-Tab nachtragen (unser eigener Diff an
   `app.js`/`index.html`, siehe Story 9.4).
4. Compose-Image-Tag mitziehen, dann
   `docker compose pull && docker compose up -d`.
5. Gegenprüfen: UI lädt, MG-Kernfunktionen (Suche/Queue/Settings)
   arbeiten, Import-Monitor-Tab erscheint, `/static/app.js` liefert 200.
