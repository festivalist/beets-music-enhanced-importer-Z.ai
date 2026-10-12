#MODULE musicgrabber|MusicGrabber (Docker-Compose, Beschaffungs-Engine)|docker detect|0
# Beschaffungs-Engine Nr. 2 aus dem Repo-Compose-File (PI-SETUP Phase 9).
# Nordstern/SCOPE: MG beschafft ausschließlich bis ins Staging
# <library>/_incoming/musicgrabber — beets/musik bleibt einzige schreibende
# Instanz der echten Bibliothek; das compose-File mountet deshalb NUR das
# Staging und bleibt unangetastet (Pfadstabilität über /mnt/music).
#
# Live-Lehren eingebaut (Phase 9.8/10): Layout-Anker (Singles/Albums/
# Playlists) HOST-seitig als Run-User anlegen — NIEMALS im Container
# (root-owned → PermissionError-Crash-Loop); Staging-Root nie löschen;
# KEIN API_KEY in der .env (sperrt die UI dauerhaft aus); PUID/PGID müssen
# dem Run-User entsprechen, sonst kann die Pipeline die Dateien nicht lesen.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$HERE/lib/common.sh"

RUN_USER="${SUDO_USER:-$(id -un)}"
RUN_UID=$(id -u "$RUN_USER"); RUN_GID=$(id -g "$RUN_USER")
MGDIR="$INSTALLER_PROJECT_DIR/musicgrabber"
MGPORT="${INSTALLER_MG_PORT:-38274}"

step "MusicGrabber (Docker)"

# 1) Musik-Root muss stehen (disks-Modul setzt ANSWER_library)
LIB=$(state_get ANSWER_library "")
[[ -z "$LIB" && -d "${INSTALLER_MUSIC_MOUNT:-/mnt/music}" ]] && LIB="${INSTALLER_MUSIC_MOUNT:-/mnt/music}"
if [[ -z "$LIB" || ! -d "$LIB" ]]; then
    info "Kein Musik-Root vorhanden — MusicGrabber braucht das Staging darunter."
    info "Nach dem Platten-Modul:  bash install.sh --only musicgrabber"
    finish skip "kein Musik-Root"
fi
STAGING="$LIB/_incoming/musicgrabber"

# 2) Staging + Layout-Anker host-seitig als Run-User (Crash-Loop-Lehre 9.8)
run sudocmd mkdir -p "$STAGING/Singles" "$STAGING/Albums" "$STAGING/Playlists"
run sudocmd chown -R "$RUN_UID:$RUN_GID" "$STAGING"
ok "Staging + Anker (Singles/Albums/Playlists) als $RUN_USER: $STAGING"

# 3) .env aus dem Example (PUID/PGID vom Run-User; KEIN API_KEY — s. compose)
if [[ ! -f "$MGDIR/.env" ]]; then
    if [[ ${INSTALLER_DRY_RUN:-0} == 1 ]]; then
        printf '    [dry-run] musicgrabber/.env: PUID=%s PGID=%s TZ=Europe/Berlin\n' "$RUN_UID" "$RUN_GID"
    else
        sed -e "s/^PUID=.*/PUID=$RUN_UID/" -e "s/^PGID=.*/PGID=$RUN_GID/" \
            "$MGDIR/.env.example" > "$MGDIR/.env" 2>/dev/null \
            || printf 'PUID=%s\nPGID=%s\nTZ=Europe/Berlin\n' "$RUN_UID" "$RUN_GID" > "$MGDIR/.env"
        ok ".env erzeugt (PUID=$RUN_UID/PGID=$RUN_GID; ohne API-Key — UI bleibt ohne Login nutzbar)"
    fi
else
    ok ".env bereits vorhanden — unverändert gelassen."
fi

# 4) Container starten (Up-To-Date-Pull nur wenn Container fehlt — 2,6-GB-Image)
cd "$MGDIR"
if sudocmd docker compose ps 2>/dev/null | grep -q "musicgrabber" && \
   sudocmd docker inspect -f '{{.State.Running}}' musicgrabber 2>/dev/null | grep -q true; then
    ok "Container läuft bereits."
else
    step "docker compose up -d (erster Start pulled das Image — 2,6 GB, kann dauern)"
    run sudocmd docker compose up -d \
        || finish fail "compose up fehlgeschlagen — 'docker compose logs' prüfen, dann --resume"
fi

# 5) HTTP-Probe mit Geduld (erster Start initialisiert)
if [[ ${INSTALLER_DRY_RUN:-0} == 1 ]]; then
    printf '    [dry-run] HTTP-Probe http://127.0.0.1:%s\n' "$MGPORT"
    finish ok "dry-run: MusicGrabber nur angedeutet"
fi
step "Warte auf Web-UI (http://127.0.0.1:$MGPORT)…"
waited=0; maxwait="${INSTALLER_MG_WAIT:-600}"
until curl -fsS -o /dev/null "http://127.0.0.1:$MGPORT" 2>/dev/null; do
    if [[ $waited -ge $maxwait ]]; then
        warn "Web-UI antwortet nach ${waited}s nicht — Logs: docker compose logs -f"
        warn "Danach erneut:  bash install.sh --only musicgrabber"
        finish fail "MG-Web-UI nicht erreichbar (Port $MGPORT)"
    fi
    sleep 10; waited=$((waited+10))
    printf '    … %ss\n' "$waited"
done
ok "Web-UI antwortet (HTTP 200 auf :$MGPORT)"

info "Quellen/Qualität (Monochrome-FLAC lossless-first, Bitrate-Schwelle) im Settings-Tab"
info "der UI pflegen — Story 1.2. Telegram-Notify: NICHT den musik-bot-Token eintragen!"
info "Update:  cd musicgrabber && docker compose pull && docker compose up -d"
finish ok "MusicGrabber läuft auf :$MGPORT (Staging: $STAGING)"
