#MODULE base|Systempakete (git, Python, ffmpeg, fpcalc, flac)|detect|1
# Grundpakete für Tool und Module. Idempotent (apt install überpringt
# vorhandene). fpcalc steckt im Paket libchromaprint-tools (6.5-Drift-Label
# korrigiert — der alte install.sh-Warntext nannte es falsch herum).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$HERE/lib/common.sh"

step "Systempakete (git, python3+venv, ffmpeg, fpcalc, flac)"

run sudocmd apt-get update -qq \
    || warn "apt-get update fehlgeschlagen (Spiegel offline?) — Installation wird trotzdem versucht."

run sudocmd apt-get install -y -qq \
        git curl unzip python3 python3-venv python3-pip \
        ffmpeg libchromaprint-tools flac \
    || { dpkg_hint=$(sudocmd apt-get install -y -qq git 2>&1 | grep -c "interrupted" || true)
         [[ $dpkg_hint -gt 0 ]] && err "Hinweis: dpkg wurde unterbrochen — sudo dpkg --configure -a, dann --resume"
         finish fail "apt-Installation der Grundpakete fehlgeschlagen — Netz/Repos prüfen und --resume"; }

ok "git, curl, unzip, python3(+venv/pip), ffmpeg, fpcalc (libchromaprint-tools), flac"
# unzip: der Deno-Installer braucht unzip oder 7z — auf Cloud-Minimal-Images
# fehlt es (Live-Fund QEMU-Matrix 2026-10-12), sonst stirbt die Deno-Fallback-
# Installation und YouTube-Downloads laufen ohne JS-Runtime ins Leere.
finish ok "Systempakete installiert"
