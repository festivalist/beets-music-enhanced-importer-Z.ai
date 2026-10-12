#MODULE plex|Plex Media Server (nativ)|detect|0
# Plex NATIV per Paket (Nutzerentscheidung 2026-10-12 — nicht containerisiert):
# erst der offizielle apt-Repo-Weg; schlägt der auf Debian-trixie am bekannten
# SHA1/sqv-Signaturproblem fehl (PI-SETUP 5.1: Plex' Key trägt nur SHA1-
# Selbstsignaturen, Sequoia lehnt seit 2026-02-01 ab), greift automatisch
# PLAN B: Repo deaktivieren und das neueste .deb arch-bewusst direkt von der
# plex.tv-API ziehen. Danach Einrichtungs-Assistenz (Claim-URL, Token aus
# Preferences.xml, plex-Block in config.yaml, Berechtigungs-Hinweis).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$HERE/lib/common.sh"

PLEX_PREFS="${INSTALLER_PLEX_PREFS:-/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Preferences.xml}"

plex_installed() {
    dpkg-query -W -f='${Status}' plexmediaserver 2>/dev/null | grep -q "install ok installed"
}

step "Plex Media Server (nativ)"

if plex_installed; then
    ok "plexmediaserver ist bereits installiert ($(dpkg-query -W -f='${Version}' plexmediaserver 2>/dev/null || echo '?'))"
else
    want=$(menu_select plex_want "Plex Media Server installieren?" \
        "Ja — Plex installieren (nativ, apt/direktes .deb)" \
        "Nein — überspringen")
    case "$want" in
        "Ja"*) : ;;
        *)  finish skip "bewusst ohne Plex" ;;
    esac

    ARCH=$(state_get ANSWER_arch "$(uname -m)")
    step "Plex-apt-Repo einrichten"
    run sudocmd apt-get install -y -qq curl gnupg >/dev/null 2>&1 || true
    echo "deb https://downloads.plex.tv/repo/deb public main" \
        | run sudocmd tee /etc/apt/sources.list.d/plexmediaserver.list >/dev/null
    if [[ ${INSTALLER_DRY_RUN:-0} != 1 ]]; then
        # --yes ist Idempotenz: ein vorhandenes plex.gpg aus einem früheren
        # Lauf würde gpg sonst interaktiv überschreiben wollen (EOF → Fail;
        # QEMU-Matrix-Live-Fund Nr. 6).
        curl -fsSL https://downloads.plex.tv/plex-keys/PlexSign.key \
            | sudocmd gpg --yes --dearmor -o /etc/apt/trusted.gpg.d/plex.gpg \
            || finish fail "Plex-Signatur-Key nicht ladbar (Netz/gpg) — --resume"
    fi

    step "apt update (Repo-Probe — SHA1-Fehler → Plan B)"
    if [[ ${INSTALLER_DRY_RUN:-0} == 1 ]]; then
        printf '    [dry-run] apt-get update + apt-get install plexmediaserver (Repo-Weg)\n'
    else
        aptout=$(sudocmd apt-get update 2>&1) || true
        if echo "$aptout" | grep -qiE 'is not bound|SHA1|sequoia'; then
            warn "Debian/trixie-SHA1-Repo-Problem erkannt (PI-SETUP 5.1) — Plan B: direktes .deb."
            sudocmd mv /etc/apt/sources.list.d/plexmediaserver.list{,.disabled} 2>/dev/null || true
            sudocmd apt-get update -qq >/dev/null 2>&1 || true
            distro=$(state_get ANSWER_os_id debian); [[ "$distro" == "raspbian" ]] && distro=debian
            url=$(curl -fsSL https://plex.tv/api/downloads/5.json | python3 -c "
import json,sys
d=json.load(sys.stdin)['computer']['Program']
print(next(r['url'] for r in d['releases']
           if r.get('distro')=='$distro' and '$ARCH' in r.get('build','')))" 2>/dev/null || true)
            [[ -n "$url" ]] || finish fail "kein Plex-.deb für $distro/$ARCH in der plex.tv-API gefunden"
            deb="/tmp/${url##*/}"
            curl -fsSL "$url" -o "$deb" || finish fail "Plex-.deb Download fehlgeschlagen"
            run sudocmd apt-get install -y -qq "$deb" \
                || finish fail "Plex-.deb-Installation fehlgeschlagen (Abhängigkeiten?)"
            info "Repo bleibt deaktiviert (.disabled) — Updates später: gleicher Weg"
            info "(bash install.sh --only plex nach Deinstallation) oder Plex-eigene Updates."
        else
            if ! echo "$aptout" | grep -q .; then aptout=$(sudocmd apt-get update 2>&1 || true); fi
            run sudocmd apt-get install -y -qq plexmediaserver \
                || finish fail "plexmediaserver-Installation fehlgeschlagen — --resume nach Analyse"
        fi
    fi
    plex_installed || finish fail "Installation lief, aber plexmediaserver fehlt — dpkg -l prüfen"
    ok "plexmediaserver installiert"
fi

# --- Einrichtungs-Assistenz -----------------------------------------------------
if have systemctl; then
    run sudocmd systemctl enable --now plexmediaserver 2>/dev/null \
        || warn "plexmediaserver-Dienst nicht aktivierbar — systemctl status plexmediaserver"
fi

ipaddr=$(hostname -I 2>/dev/null || true)
ipaddr=${ipaddr%% *}
info "Web-UI (Claim + Bibliothek):  http://${ipaddr:-<host-ip>}:32400/web"
info "Musik-Bibliothek dort auf den Musik-Root zeigen lassen (Name z. B. „Musik“ merken)."

# Token aus Preferences.xml (Server schon geclaimt?) → plex-Block in config.yaml
token=""
if [[ -r "$PLEX_PREFS" ]]; then
    token=$(sudocmd grep -oP 'PlexOnlineToken="\K[^"]+' "$PLEX_PREFS" 2>/dev/null | head -1 || true)
fi
if [[ -z "$token" ]]; then
    info "Server noch nicht geclaimt (kein PlexOnlineToken) — nach dem Claim in der Web-UI:"
    info "  bash install.sh --only plex    (holt den Token und setzt config.yaml)"
    info "Berechtigungs-Falle (5.5): Plex (User plex) braucht Leserechte auf den Musik-Root:"
    info "  sudo chmod -R o+rX <musik-root>   (oder Gruppe plex ergänzen)"
    finish ok "Plex installiert; Claim/Bibliothek offen (UI), Token folgt per --only plex"
fi
ok "Plex-Token gefunden (Server ist geclaimt)."

# plex-Block in config.yaml setzen (nur wenn config.yaml da; Backup vorher)
cfg="$INSTALLER_PROJECT_DIR/config.yaml"
if [[ -f "$cfg" ]]; then
    purl=$(ask_value plex_url "Plex-URL" "http://127.0.0.1:32400")
    psec=$(ask_value plex_section "Plex-Musik-Bibliotheksname" "Musik")
    if [[ ${INSTALLER_DRY_RUN:-0} == 1 ]]; then
        printf '    [dry-run] config.yaml: musik:plex {url: %s, token: …, section: %s}\n' "$purl" "$psec"
    else
        cp "$cfg" "$cfg.bak.$(date +%Y%m%d%H%M%S)"
        python3 - "$cfg" "$purl" "$token" "$psec" <<'PYEOF' \
            || finish fail "config.yaml-Edit fehlgeschlagen — plex-Block manuell setzen (siehe PI-SETUP 5.5)"
import re, sys
path, url, token, section = sys.argv[1:5]
lines = open(path, encoding="utf-8").read().splitlines(keepends=True)
block = [f"        url: {url}\n", f"        token: {token}\n", f"        section: {section}\n"]
out, i, done, in_musik, in_plex = [], 0, False, False, False
while i < len(lines):
    ln = lines[i]
    stripped = ln.strip()
    indent = len(ln) - len(ln.lstrip())
    if re.match(r"^\S", ln):                      # Top-Level-Schlüssel
        in_musik = stripped.startswith("musik:")
        in_plex = False
    elif in_musik and stripped == "plex:":
        in_plex = True
        out.append(ln); i += 1
        j = i
        while j < len(lines) and (lines[j].strip().startswith("#") or
                                  re.match(r"^\s*(url|token|section|playlists|playlist_attempts|playlist_wait|playlist_dir):", lines[j])):
            j += 1                                # alte (kommentierte) Platzhalter ersetzen
        out.extend(block); done = True; i = j
        continue
    out.append(ln); i += 1
if not done:                                      # kein plex:-Block → unter musik: einfügen
    fixed = []
    for ln in out:
        fixed.append(ln)
        if re.match(r"^musik:", ln):
            fixed.append("    plex:\n"); fixed.extend(block); done = True
    out = fixed
if not done:
    sys.exit("kein musik:-Block gefunden")
open(path, "w", encoding="utf-8", newline="").writelines(out)
PYEOF
        ok "config.yaml: musik:plex gesetzt (url/token/section) — Backup liegt neben der config."
    fi
else
    info "config.yaml existiert noch nicht (musik-Modul noch nicht gelaufen) — plex-Block"
    info "später setzen:  bash install.sh --only plex"
fi

info "Remote Access für Plexamp von unterwegs: in der Web-UI aktivieren (5.6)."
finish ok "Plex bereit + config.yaml verdrahtet"
