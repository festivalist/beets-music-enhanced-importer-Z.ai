#MODULE samba|SMB-Freigabe „Musik“ (ohne-OMV-Pfad)|detect|0
# SMB-Share auf dem Musik-Root, damit drop-here.bat (\\<host>\Musik\_incoming\
# windows) und andere Geräte die Bibliothek erreichen — das ohne-OMV-Äquivalent
# zur OMV-SMB-Freigabe. Live-Lektion Phase 10 übernommen: force user = <user>,
# sonst dürfen Gäste nicht in die vom Ingest (User, 755) angelegte Dropzone
# schreiben. Gast-Zugriff nur LAN-seitig sinnvoll — kein Port-Forwarding.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$HERE/lib/common.sh"

SMBCONF="${INSTALLER_SMBCONF:-/etc/samba/smb.conf}"
SHARE_NAME="Musik"
RUN_USER="${SUDO_USER:-$(id -un)}"
MARKER="# --- musik-installer share (idempotent) ---"

step "SMB-Freigabe „$SHARE_NAME“ (ohne-OMV-Pfad)"

# OMV vorhanden → OMV verwaltet SMB selbst (nichts anfassen)
if dpkg-query -W -f='${Status}' openmediavault 2>/dev/null | grep -q "install ok installed"; then
    info "OpenMediaVault ist installiert — SMB/Freigaben verwaltet die OMV-UI."
    info "Dort: Musik-Freigabe anlegen, Zusatzoption force user = $RUN_USER."
    finish skip "OMV verwaltet SMB"
fi

# Musik-Root bestimmen (disks-Modul setzt ANSWER_library; Fallback /mnt/music)
LIB=$(state_get ANSWER_library "")
[[ -z "$LIB" && -d "${INSTALLER_MUSIC_MOUNT:-/mnt/music}" ]] && LIB="${INSTALLER_MUSIC_MOUNT:-/mnt/music}"
if [[ -z "$LIB" ]]; then
    info "Kein Musik-Root bekannt (disks-Modul noch nicht gelaufen oder ohne Platte)."
    info "Nach dem Einbinden:  bash install.sh --only samba"
    finish skip "kein Musik-Root vorhanden"
fi
if [[ ! -d "$LIB" ]]; then
    err "Musik-Root '$LIB' existiert nicht — Freigabe würde ins Leere zeigen."
    finish fail "Musik-Root fehlt: $LIB"
fi

# Samba installieren (idempotent)
if ! have smbd && ! dpkg-query -W -f='${Status}' samba 2>/dev/null | grep -q "install ok installed"; then
    run sudocmd apt-get install -y -qq samba \
        || finish fail "samba-Installation fehlgeschlagen — --resume nach Behebung"
fi
ok "samba installiert (Root: $LIB)"

# Share-Block idempotent hinterlegen
if grep -q "$MARKER" "$SMBCONF" 2>/dev/null; then
    ok "Freigabe „$SHARE_NAME“ ist bereits konfiguriert (Marker vorhanden)."
else
    if [[ ${INSTALLER_DRY_RUN:-0} == 1 ]]; then
        printf '    [dry-run] smb.conf += [%s] path=%s force user=%s guest\n' "$SHARE_NAME" "$LIB" "$RUN_USER"
    else
        bak="$SMBCONF.bak.$(date +%Y%m%d%H%M%S)"
        sudocmd cp "$SMBCONF" "$bak"
        # „map to guest = Bad User“ global nötig, damit Gast-Zugriff ohne Konto
        # klappt — in den BESTEHENDEN [global]-Block einfügen (kein Dublett-
        # Abschnitt am Dateiende, den testparm/Samba nicht dulden).
        if ! grep -q "map to guest" "$SMBCONF"; then
            if grep -q '^\[global\]' "$SMBCONF"; then
                sudocmd sed -i '/^\[global\]/a\   map to guest = Bad User' "$SMBCONF"
            else
                printf '\n[global]\n   map to guest = Bad User\n' | sudocmd tee -a "$SMBCONF" >/dev/null
            fi
        fi
        cat <<EOF | sudocmd tee -a "$SMBCONF" >/dev/null

$MARKER
[$SHARE_NAME]
   path = $LIB
   read only = no
   browseable = yes
   guest ok = yes
   force user = $RUN_USER
   create mask = 0644
   directory mask = 0755
EOF
        ok "Freigabe angelegt (Backup: $bak)"
    fi
fi

if have systemctl; then
    run sudocmd systemctl enable --now smbd
    if ! sudocmd systemctl is-active smbd >/dev/null 2>&1; then
        warn "smbd ist nicht aktiv — Log: journalctl -u smbd -n 20"
        finish fail "smbd startet nicht"
    fi
    ok "smbd läuft"
else
    run sudocmd service smbd restart || warn "smbd-Restart fehlgeschlagen — manuell prüfen."
fi

# Probe: Port 445 lauscht?
if have ss && ss -ltn 2>/dev/null | grep -q ':445 '; then
    ok "Port 445 lauscht."
else
    warn "Port 445 nicht als lauschend erkannt (ss fehlt oder smbd noch am Starten)."
fi

info "Windows-Ablage (drop-here.bat):  \\\\$(hostname)\\$SHARE_NAME\\_incoming\\windows"
info "Nur im LAN nutzen — kein Port-Forwarding für 445."
finish ok "SMB-Freigabe $SHARE_NAME → $LIB (force user=$RUN_USER)"
