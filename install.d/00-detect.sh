#MODULE detect|Systemerkennung (OS & Architektur)||1
# Erkennt Host-Betriebssystem und -Architektur und entscheidet, welche
# Installationspfade offenstehen (OMV nur auf Debian/Raspberry Pi OS —
# Nutzerentscheidung 2026-10-12: Ubuntu bekommt den ohne-OMV-Pfad, kein Hack).
# Läuft rein lesend; bricht auf nicht unterstützten Systemen SAUBER ab,
# bevor irgendeine Änderung am Host passiert.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$HERE/lib/common.sh"

step "Systemerkennung"

if [[ ! -r /etc/os-release ]]; then
    err "Kein /etc/os-release gefunden — dieses System ist kein Linux im Debian-Stil"
    err "(Windows/macOS/BSD?). Der Installer benötigt Debian, Raspberry Pi OS oder Ubuntu."
    finish fail "nicht unterstütztes Betriebssystem"
fi
. /etc/os-release   # setzt ID, VERSION_ID, VERSION_CODENAME, PRETTY_NAME, ggf. ID_LIKE

ARCH_RAW=$(uname -m)
case "$ARCH_RAW" in
    x86_64|amd64)   ARCH=amd64 ;;
    aarch64|arm64)  ARCH=arm64 ;;
    *)  err "Architektur '$ARCH_RAW' wird nicht unterstützt (nur amd64/arm64 —"
        err "Docker-Compose-Binary, Plex- und Deno-Download sind darauf begrenzt)."
        finish fail "Architektur $ARCH_RAW nicht unterstützt" ;;
esac

if ! have apt-get; then
    finish fail "kein apt-get gefunden — Debian/Ubuntu-Familie erforderlich"
fi

OS_ID="${ID:-unknown}"
OS_VERSION="${VERSION_ID:-?}"
OS_CODENAME="${VERSION_CODENAME:-unbekannt}"
OMV_OK=0
case "$OS_ID" in
    debian|raspbian)
        OMV_OK=1 ;;
    ubuntu)
        OMV_OK=0 ;;   # OMV offiziell nur Debian — ehrlich ablehnen statt hacken
    *)
        case " ${ID_LIKE:-} " in
            *" debian "*)
                warn "Unbekannte Distribution '$PRETTY_NAME' (ID_LIKE enthält debian)."
                warn "Weiterlauf auf eigenes Risiko; OMV wird auf diesem System nicht angeboten."
                ;;
            *)
                finish fail "Distribution '$OS_ID' wird nicht unterstützt (Debian/RasPiOS/Ubuntu)" ;;
        esac ;;
esac

# Ressourcen-Vorwarnung (kein Abbruch — kleine Boxen laufen, nur enger)
RAM_MB=$(awk '/^MemTotal:/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)
if [[ "$RAM_MB" -gt 0 && "$RAM_MB" -lt 2000 ]]; then
    warn "Nur ${RAM_MB} MB RAM — Plex + MusicGrabber zusammen mögen deutlich mehr."
fi
ROOT_FREE_GB=$(df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9' || echo 0)
if [[ "$ROOT_FREE_GB" -gt 0 && "$ROOT_FREE_GB" -lt 5 ]]; then
    warn "Nur ${ROOT_FREE_GB} GB frei auf / — venv, Docker-Images und Plex wollen mehr."
fi

state_set ANSWER_os_id "$OS_ID"
state_set ANSWER_os_version "$OS_VERSION"
state_set ANSWER_os_codename "$OS_CODENAME"
state_set ANSWER_arch "$ARCH"
state_set ANSWER_omv_supported "$OMV_OK"

ok "System: ${PRETTY_NAME:-$OS_ID $OS_VERSION} ($ARCH)"
ok "OMV-Installation: $([[ $OMV_OK == 1 ]] && echo 'möglich (Debian-Familie)' || echo 'nicht vorgesehen (Ubuntu → ohne-OMV-Pfad)')"
finish ok "${PRETTY_NAME:-$OS_ID}, $ARCH, OMV=$OMV_OK"
