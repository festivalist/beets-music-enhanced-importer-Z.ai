#MODULE docker|Docker-Engine + Compose v2|detect|0
# Docker für MusicGrabber (und spätere Mitbewohner wie Tandoor/Immich —
# die Modul-Registry bleibt offen, Stories später). Bewusst Distribution-
# Pakete (docker.io) statt Fremd-Repo (Debian-Entscheidung aus PI-SETUP 9.1)
# und das Compose-v2-Plugin als Standalone-Binary von GitHub — arch-bewusst
# (aarch64/x86_64 statt des bislang hartkodierten aarch64 aus 9.1).
# Live-Falle aus 7.3: auf trixie ist docker-cli nur ein RECOMMENDS von
# docker.io — mit Install-Recommends=false (OMV-apt!) fehlt das CLI danach;
# wird hier explizit mitinstalliert.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$HERE/lib/common.sh"

RUN_USER="${SUDO_USER:-$(id -un)}"

step "Docker-Engine + Compose v2"

want=$(menu_select docker_want "Docker installieren? (MusicGrabber braucht es)" \
    "Ja — Docker + Compose installieren" \
    "Nein — überspringen (MusicGrabber-Modul wird dann übersprungen)")
case "$want" in
    "Ja"*) : ;;
    *)  finish skip "bewusst ohne Docker" ;;
esac

# 1) Engine + CLI aus Distributionsquellen (idempotent)
if have docker; then
    ok "docker bereits vorhanden: $(docker --version 2>/dev/null || echo '?')"
else
    run sudocmd apt-get update -qq || true
    # docker-cli explizit: auf trixie nur Recommends (OMV-apt lässt es weg)
    run sudocmd apt-get install -y -qq docker.io docker-cli \
        || finish fail "docker.io-Installation fehlgeschlagen — Repos/Netz prüfen, dann --resume"
    ok "docker.io + docker-cli installiert"
fi
if have systemctl; then
    run sudocmd systemctl enable --now docker
    if ! sudocmd systemctl is-active docker >/dev/null 2>&1; then
        finish fail "docker-Dienst startet nicht — journalctl -u docker -n 30"
    fi
    ok "docker-Dienst läuft"
fi

# 2) Compose v2 als CLI-Plugin, arch-bewusst (9.1-Logik, parametrisiert)
ARCH=$(state_get ANSWER_arch "$(uname -m)")
case "$ARCH" in
    arm64)  COMPOSE_ARCH=aarch64 ;;
    amd64)  COMPOSE_ARCH=x86_64 ;;
    *) finish fail "Architektur $ARCH für Compose-Binary unbekannt" ;;
esac
COMPOSE_BIN="${INSTALLER_COMPOSE_DIR:-/usr/local/lib/docker/cli-plugins}/docker-compose"
if sudocmd docker compose version >/dev/null 2>&1; then
    ok "docker compose bereits nutzbar: $(sudocmd docker compose version 2>/dev/null | head -1)"
elif [[ -x "$COMPOSE_BIN" ]]; then
    ok "Compose-Binary vorhanden: $COMPOSE_BIN"
else
    url="https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$COMPOSE_ARCH"
    if [[ ${INSTALLER_DRY_RUN:-0} == 1 ]]; then
        printf '    [dry-run] curl -fsSL %s -o %s\n' "$url" "$COMPOSE_BIN"
    else
        run sudocmd mkdir -p /usr/local/lib/docker/cli-plugins
        run sudocmd curl -fsSL "$url" -o "$COMPOSE_BIN" \
            || finish fail "Compose-Binary nicht ladbar ($url) — GitHub erreichbar? --resume"
        run sudocmd chmod +x "$COMPOSE_BIN"
        sudocmd docker compose version >/dev/null 2>&1 \
            || finish fail "Compose-Binary installiert, aber 'docker compose version' schlägt fehl"
        ok "Compose v2 installiert ($(sudocmd docker compose version 2>/dev/null | head -1))"
    fi
fi

# 3) Run-User in die docker-Gruppe (sonst nur sudo-Docker)
if [[ "$RUN_USER" != root ]] && ! id -nG "$RUN_USER" 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
    run sudocmd usermod -aG docker "$RUN_USER"
    info "$RUN_USER ist jetzt in der docker-Gruppe — einmal NEU ANMELDEN (oder newgrp docker),"
    info "danach funktioniert 'docker compose' auch ohne sudo."
else
    ok "$RUN_USER darf docker direkt nutzen (Gruppe docker)"
fi

finish ok "Docker + Compose v2 bereit (arch=$ARCH)"
