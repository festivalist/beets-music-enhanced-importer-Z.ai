#MODULE verify|Abschlussprüfung (Report-Karte)|detect|0
# Read-only-Gesundcheck nach der Installation: tastet jede Komponente real
# ab (nicht dem State glauben) und druckt eine Report-Karte ✓/✗/– plus die
# Liste der bewusst manuell offenen Schritte. Das Modul selbst failt nie —
# es diagnostiziert nur; der Treiber zeigt die Karte in der Zusammenfassung.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$HERE/lib/common.sh"

RUN_USER="${SUDO_USER:-$(id -un)}"
LIB=$(state_get ANSWER_library "")
[[ -z "$LIB" && -d "${INSTALLER_MUSIC_MOUNT:-/mnt/music}" ]] && LIB="${INSTALLER_MUSIC_MOUNT:-/mnt/music}"
MANUAL_OPEN=()

mark() { # zustand text → Zeile der Report-Karte
    printf '  %s %s\n' "$1" "$2"
}
probe() { printf '    … %s\n' "$1"; }

step "Report-Karte"

# --- Musik-Root ----------------------------------------------------------------
MUSIC_OK=0
if [[ -n "$LIB" && -d "$LIB" ]]; then
    MUSIC_OK=1
    if findmnt "$LIB" >/dev/null 2>&1; then
        mark "✓" "Musik-Root $LIB (gemountet: $(findmnt -no FSTYPE "$LIB" 2>/dev/null || echo '?'))"
    elif [[ -L "$LIB" ]]; then
        mark "✓" "Musik-Root $LIB (Symlink → $(readlink -f "$LIB"))"
    else
        mark "✓" "Musik-Root $LIB (lokaler Ordner)"
    fi
    if as_user "$RUN_USER" touch "$LIB/.verify-probe" 2>/dev/null; then
        rm -f "$LIB/.verify-probe"
    else
        mark "✗" "Schreibrechte fehlen: $RUN_USER darf nicht in $LIB schreiben"
    fi
else
    mark "—" "kein Musik-Root (Platte fehlt — bash install.sh --add-disk)"
    MANUAL_OPEN+=("Musik-Platte einbauen und: bash install.sh --add-disk")
fi

# --- musik-Tool ------------------------------------------------------------------
PY="$INSTALLER_PROJECT_DIR/.venv/bin/python"
if [[ -e "$PY" && -f "$INSTALLER_PROJECT_DIR/config.yaml" ]]; then
    mark "✓" "musik-Tool (venv + config.yaml vorhanden)"
    if [[ ! -f "$INSTALLER_PROJECT_DIR/telegram_token.json" ]]; then
        MANUAL_OPEN+=("Telegram-Bot-Token fehlt: telegram_token.json ({\"token\": \"…\"}) — sonst idled der Bot mit Fehlern")
    fi
    if [[ ! -f "$INSTALLER_PROJECT_DIR/cookies.txt" ]]; then
        MANUAL_OPEN+=("YouTube-Premium-Cookies fehlen (PI-SETUP Phase 3) — sonst 128 kbps statt 256")
    fi
    allow=$(grep -A2 'bot_allowlist' "$INSTALLER_PROJECT_DIR/config.yaml" 2>/dev/null | grep -o '[0-9]\{6,\}' | head -1 || true)
    [[ -n "$allow" ]] || MANUAL_OPEN+=("Bot-Allowlist leer: dem Bot einmal schreiben, Chat-ID aus der Antwort in config.yaml (musik: bot_allowlist) übernehmen")
else
    mark "✗" "musik-Tool unvollständig (venv oder config.yaml fehlt) — bash install.sh --only musik"
fi

# --- systemd-Einheiten -------------------------------------------------------------
if have systemctl; then
    for u in musik-bot.service musik-ingest.timer; do
        if sudocmd systemctl is-enabled "$u" >/dev/null 2>&1; then
            if sudocmd systemctl is-active "$u" >/dev/null 2>&1; then
                mark "✓" "$u (enabled + aktiv)"
            else
                mark "✓" "$u (enabled; startet beim Boot — systemctl start $u)"
            fi
        else
            mark "—" "$u nicht installiert (--only musik)"
        fi
    done
else
    mark "—" "kein systemd (Container/Wsx?) — Bot/Timer manuell starten"
fi

# --- Docker + MusicGrabber ----------------------------------------------------------
if have docker && sudocmd docker info >/dev/null 2>&1; then
    mark "✓" "Docker ($(sudocmd docker --version 2>/dev/null | cut -d, -f1))"
    if sudocmd docker inspect -f '{{.State.Running}}' musicgrabber 2>/dev/null | grep -q true; then
        if curl -fsS -o /dev/null "http://127.0.0.1:${INSTALLER_MG_PORT:-38274}" 2>/dev/null; then
            mark "✓" "MusicGrabber (Container läuft, Web-UI antwortet)"
        else
            mark "✗" "MusicGrabber-Container läuft, aber Web-UI antwortet nicht"
        fi
    else
        mark "—" "MusicGrabber nicht gestartet (--only musicgrabber)"
    fi
else
    mark "—" "Docker nicht installiert/gestartet (--only docker)"
fi

# --- Plex ------------------------------------------------------------------------------
if dpkg-query -W -f='${Status}' plexmediaserver 2>/dev/null | grep -q "install ok installed"; then
    if curl -fsS -o /dev/null -m 4 "http://127.0.0.1:32400/identity" 2>/dev/null; then
        mark "✓" "Plex Media Server (API antwortet auf :32400)"
    else
        mark "✗" "Plex installiert, aber API antwortet nicht (systemctl status plexmediaserver)"
    fi
    PLEX_PREFS="${INSTALLER_PLEX_PREFS:-/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Preferences.xml}"
    if ! sudocmd grep -q 'PlexOnlineToken=' "$PLEX_PREFS" 2>/dev/null; then
        MANUAL_OPEN+=("Plex claimen: http://<host-ip>:32400/web — danach bash install.sh --only plex (Token + config.yaml)")
    fi
    if ! grep -qE '^\s*section:' "$INSTALLER_PROJECT_DIR/config.yaml" 2>/dev/null; then
        MANUAL_OPEN+=("Plex-Musik-Bibliothek in der Web-UI auf den Musik-Root zeigen lassen (Name = plex.section in config.yaml, z. B. „Musik“) — danach --only plex")
    fi
else
    mark "—" "Plex nicht installiert (--only plex)"
fi

# --- SMB/Dropzone ------------------------------------------------------------------------
SMBCONF="${INSTALLER_SMBCONF:-/etc/samba/smb.conf}"
if dpkg-query -W -f='${Status}' openmediavault 2>/dev/null | grep -q "install ok installed"; then
    mark "✓" "OpenMediaVault verwaltet Freigaben (Share „Musik“ mit force user in der UI prüfen)"
    if [[ $MUSIC_OK != 1 ]]; then
        MANUAL_OPEN+=("OMV: Musik-Freigabe anlegen/prüfen (force user = $RUN_USER), dann bash install.sh --only disks")
    fi
elif have smbd || grep -q "^\[Musik\]" "$SMBCONF" 2>/dev/null; then
    if sudocmd systemctl is-active smbd >/dev/null 2>&1; then
        mark "✓" "SMB-Freigabe Musik (smbd aktiv) — Windows-Ablage: \\\\$(hostname)\\Musik\\_incoming\\windows"
    else
        mark "✗" "SMB konfiguriert, aber smbd inaktiv (systemctl start smbd)"
    fi
else
    mark "—" "keine SMB-Freigabe (--only samba) — drop-here.bat braucht sie"
fi

# --- Manuell offene Punkte ---------------------------------------------------------------
if [[ ${#MANUAL_OPEN[@]} -gt 0 ]]; then
    step "Manuell offen (bewusste UI-/Einmal-Schritte)"
    i=0
    for m in "${MANUAL_OPEN[@]}"; do i=$((i+1)); printf '    %d) %s\n' "$i" "$m"; done
else
    ok "Keine manuellen Schritte offen — System vollständig verdrahtet."
fi

step "Empfehlung: Gesundcheck der Bibliothek"
info ".venv/bin/python musik.py doctor --quick --limit 50    (Decode-Spot-Check; ohne --limit dauert der ERSTE Lauf Stunden)"
finish ok "Report-Karte erstellt"
