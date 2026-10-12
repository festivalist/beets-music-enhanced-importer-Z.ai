#MODULE musik|musik-Tool (venv, spotDL/SomeDL, Deno, systemd-Bot+Timer)|detect base|1
# Der klassische install.sh-Kern (EPIC 8: in ein Modul überführt, Verhalten
# unverändert — --library/--no-systemd bleiben wirksam, config.yaml wird bei
# Wiederholungsläufen nie angetastet, Tokens/State bleiben unberührt).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$HERE/lib/common.sh"

PROJECT_DIR="$INSTALLER_PROJECT_DIR"
cd "$PROJECT_DIR"

NO_SYSTEMD=0
[[ ${INSTALLER_NO_SYSTEMD:-0} == 1 ]] && NO_SYSTEMD=1
LIBRARY_ARG=$(state_get ANSWER_library "")

# --- Python version check ------------------------------------------------------
step "Checking Python >= 3.10"
PY_OK=0
for PY in python3 python; do
    if have "$PY"; then
        if "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
            PYTHON="$PY"; PY_OK=1; break
        fi
    fi
done
[[ $PY_OK -eq 1 ]] || finish fail "Python 3.10+ erforderlich (apt: python3 python3-venv)"
ok "using $($PYTHON --version)"

# --- Virtual environment + dependencies ----------------------------------------
step "Creating virtual environment (.venv)"
if [[ ! -d .venv ]]; then
    run "$PYTHON" -m venv .venv
fi
PY_EXE="$PROJECT_DIR/.venv/bin/python"
[[ -x "$PY_EXE" ]] || finish fail "venv angelegt, aber $PY_EXE fehlt — manuell prüfen"
run "$PY_EXE" -m pip install --upgrade pip --quiet
step "Installing dependencies (beets, spotdl, somedl, telegram bot)"
run "$PY_EXE" -m pip install -r requirements.txt \
    || finish fail "pip install -r requirements.txt fehlgeschlagen — --resume nach Behebung"
ok "dependencies installed"

step "Downloading Deno runtime (yt-dlp needs it for some YouTube videos)"
run "$PY_EXE" -m spotdl --download-deno \
    || echo "    WARNING: Deno download failed - some YouTube tracks may fail."

# spotdl hides its Deno in ~/.spotdl — only spotdl itself finds it there.
# SomeDL/yt-dlp need a JS runtime ON PATH to solve YouTube's n-challenge
# (without it every YouTube download dies with "Requested format is not
# available" after "n challenge solving failed"). Best effort:
DENO_SRC=""
for cand in "$HOME/.spotdl/deno" "$HOME/.deno/bin/deno"; do
    [[ -x "$cand" ]] && DENO_SRC="$cand" && break
done
if [[ -z "$DENO_SRC" ]] && ! have deno; then
    # spotdl's deno download fails on some platforms (aarch64!) — fall
    # back to the official installer (supports linux arm64)
    step "spotdl-Deno fehlt — offizieller Deno-Installer (aarch64-kompatibel)"
    run curl -fsSL https://deno.land/install.sh | run sh -s -- -y \
        || echo "    WARNING: Deno-Installer fehlgeschlagen — YouTube-Downloads werden scheitern."
    [[ -x "$HOME/.deno/bin/deno" ]] && DENO_SRC="$HOME/.deno/bin/deno"
fi
if [[ -n "$DENO_SRC" ]] && ! have deno; then
    if run sudocmd cp "$DENO_SRC" /usr/local/bin/deno 2>/dev/null; then
        ok "deno -> /usr/local/bin/deno (systemweit sichtbar, auch für den systemd-Service)"
    elif cp "$DENO_SRC" "$PROJECT_DIR/bin/deno" 2>/dev/null; then
        echo "    Hinweis: deno nach bin/ kopiert (musik-Prozesse finden ihn über den"
        echo "    PATH-Bootstrap); für manuelle yt-dlp-Aufrufe: PATH um bin/ ergänzen."
    fi
elif have deno; then
    ok "deno already on PATH: $(command -v deno)"
fi

# --- Setup wizard (before the self test: fetch needs config.yaml) --------------
if [[ -f "$PROJECT_DIR/config.yaml" ]]; then
    step "config.yaml already exists - keeping it (re-run 'musik setup' to regenerate)"
elif [[ ${INSTALLER_DRY_RUN:-0} == 1 ]]; then
    step "Dry-Run: Setup-Wizard übersprungen (er würde config.yaml schreiben)"
else
    step "Setup wizard: library root, Discogs token, Telegram bot token"
    if [[ -n "$LIBRARY_ARG" ]]; then
        "$PY_EXE" musik.py setup --library "$LIBRARY_ARG"
    else
        "$PY_EXE" musik.py setup
    fi
fi

# --- Self test -------------------------------------------------------------------
if [[ ${INSTALLER_DRY_RUN:-0} == 1 ]]; then
    step "Dry-Run: Self-Test übersprungen (venv ggf. nicht real installiert)"
else
    step "Self test (spotdl / somedl / ffmpeg / fpcalc)"
    "$PY_EXE" musik.py fetch --self-test \
        || finish fail "Self-Test fehlgeschlagen — Ursache beheben, dann --resume"
fi

# The ingest unit flocks state/ingest.lock; the app creates state/ only
# lazily on its first state write — on a fresh box the timer failed with
# EX_NOINPUT until then (live case EPIC 7 migration, 2026-10-10).
mkdir -p "$PROJECT_DIR/state"

# --- systemd service for the bot + ingest timer ----------------------------------
if [[ $NO_SYSTEMD -eq 0 ]] && have systemctl; then
    step "Installing systemd service (musik-bot.service)"
    RUN_USER="${SUDO_USER:-$(id -un)}"
    RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
    UNIT=/etc/systemd/system/musik-bot.service
    sudocmd tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=musik telegram bot (link -> download -> beets import)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$PROJECT_DIR
# -u is load-bearing: without it Python block-buffers stdout under
# systemd and journalctl stays silent about job progress (only stderr
# like tracebacks shows up).
ExecStart=$PROJECT_DIR/.venv/bin/python -u musik.py bot
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF
    sudocmd systemctl daemon-reload
    sudocmd systemctl enable musik-bot.service
    ok "enabled (starts on boot). Config check:"
    ok "  1. telegram_token.json present?  systemctl start musik-bot"
    ok "  2. journal: journalctl -u musik-bot -f"
    [[ -f "$PROJECT_DIR/telegram_token.json" ]] || \
        echo "    note: no telegram_token.json yet — service will idle-error until created."

    step "Installing ingest timer (musik-ingest: MusicGrabber staging -> beets -> Plex)"
    # flock -n: skip if a previous run still holds the lock (long imports);
    # the bot does not take this lock — a rare collision errors one side,
    # the timer simply retries 15 minutes later.
    sudocmd tee /etc/systemd/system/musik-ingest.service >/dev/null <<EOF
[Unit]
Description=musik ingest (MusicGrabber staging -> beets -> Plex)
After=network-online.target

[Service]
Type=oneshot
User=$RUN_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/flock -n $PROJECT_DIR/state/ingest.lock $PROJECT_DIR/.venv/bin/python -u musik.py ingest
EOF
    sudocmd tee /etc/systemd/system/musik-ingest.timer >/dev/null <<EOF
[Unit]
Description=run musik ingest every 15 minutes

[Timer]
OnCalendar=*:0/15
Persistent=true

[Install]
WantedBy=timers.target
EOF
    sudocmd systemctl daemon-reload
    sudocmd systemctl enable --now musik-ingest.timer
    ok "musik-ingest.timer enabled (every 15 min; manual: musik.py ingest)"
else
    step "Skipping systemd service (--no-systemd or no systemctl)"
fi

step "musik-Tool bereit."
cat <<'EOF'

  music library   : see config.yaml (directory:)
  telegram bot    : systemctl start musik-bot   (or: .venv/bin/python musik.py bot)
  manual fetch    : .venv/bin/python musik.py fetch --import "<spotify/youtube link>"
  health check    : .venv/bin/python musik.py doctor --quick

Reports land in reports/, finished albums in your library root.
Read README.md for the full workflow and the bot setup.
EOF
finish ok "musik-Tool installiert (venv + systemd)"
