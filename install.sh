#!/usr/bin/env bash
# musik installer for Linux / Raspberry Pi OS (Debian-based).
# Parity with install.ps1: Python >= 3.10, venv, pip deps, native tools,
# setup wizard, and a systemd service for the Telegram bot.
#
# Usage:  bash install.sh [--no-systemd] [--library /mnt/music]
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

NO_SYSTEMD=0
LIBRARY_ARG=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-systemd) NO_SYSTEMD=1; shift ;;
        --library) LIBRARY_ARG="${2:?--library needs a path}"; shift 2 ;;
        *) echo "unknown option: $1"; exit 1 ;;
    esac
done

step() { printf '\n==> %s\n' "$1"; }
ok()   { printf '    %s\n' "$1"; }

# --- 1. System packages ------------------------------------------------------
step "Installing system packages (python3-venv, ffmpeg, fpcalc, flac)"
SUDO=""
if [[ $EUID -ne 0 ]]; then SUDO="sudo"; fi
if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq python3 python3-venv python3-pip \
        ffmpeg libchromaprint-tools flac
    ok "system packages installed"
else
    echo "    WARNING: no apt-get found — install python3(>=3.10)+venv, ffmpeg,"
    echo "    fpcalc (libchromaprint-tools) and flac manually, then re-run."
fi

# --- 2. Python version check -------------------------------------------------
step "Checking Python >= 3.10"
PY_OK=0
for PY in python3 python; do
    if command -v "$PY" >/dev/null 2>&1; then
        if "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
            PYTHON="$PY"; PY_OK=1; break
        fi
    fi
done
[[ $PY_OK -eq 1 ]] || { echo "Python 3.10+ required (apt: python3 python3-venv)."; exit 1; }
ok "using $($PYTHON --version)"

# --- 3. Virtual environment + dependencies -----------------------------------
step "Creating virtual environment (.venv)"
[[ -d .venv ]] || "$PYTHON" -m venv .venv
PY_EXE="$PROJECT_DIR/.venv/bin/python"
"$PY_EXE" -m pip install --upgrade pip --quiet
step "Installing dependencies (beets, spotdl, somedl, telegram bot)"
"$PY_EXE" -m pip install -r requirements.txt
ok "dependencies installed"

step "Downloading Deno runtime (yt-dlp needs it for some YouTube videos)"
"$PY_EXE" -m spotdl --download-deno \
    || echo "    WARNING: Deno download failed - some YouTube tracks may fail."

# --- 4. Self test -------------------------------------------------------------
step "Self test (spotdl / somedl / ffmpeg / fpcalc)"
"$PY_EXE" musik.py fetch --self-test

# --- 5. Setup wizard ----------------------------------------------------------
if [[ -f "$PROJECT_DIR/config.yaml" ]]; then
    step "config.yaml already exists - keeping it (re-run 'musik setup' to regenerate)"
else
    step "Setup wizard: library root, Discogs token, Telegram bot token"
    if [[ -n "$LIBRARY_ARG" ]]; then
        "$PY_EXE" musik.py setup --library "$LIBRARY_ARG"
    else
        "$PY_EXE" musik.py setup
    fi
fi

# --- 6. systemd service for the bot -------------------------------------------
if [[ $NO_SYSTEMD -eq 0 ]] && command -v systemctl >/dev/null 2>&1; then
    step "Installing systemd service (musik-bot.service)"
    RUN_USER="${SUDO_USER:-$(id -un)}"
    RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
    UNIT=/etc/systemd/system/musik-bot.service
    $SUDO tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=musik telegram bot (link -> download -> beets import)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python musik.py bot
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable musik-bot.service
    ok "enabled (starts on boot). Config check:"
    ok "  1. telegram_token.json present?  systemctl start musik-bot"
    ok "  2. journal: journalctl -u musik-bot -f"
    [[ -f "$PROJECT_DIR/telegram_token.json" ]] || \
        echo "    note: no telegram_token.json yet — service will idle-error until created."
else
    step "Skipping systemd service (--no-systemd or no systemctl)"
fi

# --- 7. Done -------------------------------------------------------------------
step "Ready."
cat <<'EOF'

  music library   : see config.yaml (directory:)
  telegram bot    : systemctl start musik-bot   (or: .venv/bin/python musik.py bot)
  manual fetch    : .venv/bin/python musik.py fetch --import "<spotify/youtube link>"
  health check    : .venv/bin/python musik.py doctor --quick

Reports land in reports/, finished albums in your library root.
Read README.md for the full workflow and the bot setup.
EOF
