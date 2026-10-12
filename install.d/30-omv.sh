#MODULE omv|OpenMediaVault (optional, nur Debian-Familie)|detect|0
# OMV gehört auf diesen Host NUR, wenn das System Debian/Raspberry Pi OS ist
# (Nutzerentscheidung 2026-10-12: kein OMV-auf-Ubuntu-Hack). OMV wird NATIV
# installiert (nie Docker — es verwaltet den Host selbst) über das offizielle
# InstallScript der OpenMediaVault-Plugin-Developers.
#
# Warnung vorab (ehrlich, weil Bruch möglich): das OMV-InstallScript
#   - läuft 10–20 Minuten und übernimmt apt-/Netzwerkkonfiguration,
#   - HÄRTET SSH (root-Login aus, teils Passwort-Login aus) — vorher
#     sicherstellen, dass ein Key-Login als Sudo-User funktioniert,
#   - ist nur für ein SAUBERES Debian/minimales RasPiOS gedacht; auf
#     vorbelasteten Systemen kann es bestehende Dienste umbiegen.
# Platten/Shares verwaltet danach OMV selbst (UI); der Installer verdrahtet
# nur die Integration (/mnt/music-Symlink — Story 8.2, disks-Modul).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$HERE/lib/common.sh"

OMV_INSTALL_URL="https://github.com/OpenMediaVault-Plugin-Developers/installScript/raw/master/install"

omv_installed() {
    dpkg-query -W -f='${Status}' openmediavault 2>/dev/null | grep -q "install ok installed" \
        || have omv-confdb
}

step "OpenMediaVault"

# 1) Ubuntu & Co.: ehrlich ablehnen, auf den ohne-OMV-Pfad verweisen
if [[ "$(state_get ANSWER_omv_supported 0)" != "1" ]]; then
    osname=$(state_get ANSWER_os_id "diesem System")
    info "OMV unterstützt offiziell nur Debian/Raspberry Pi OS — hier: $osname."
    info "Der ohne-OMV-Pfad ist gleichwertig: Festplatten per fstab (disks-Modul),"
    info "SMB-Freigabe übernimmt das samba-Modul (Modul 32)."
    finish skip "OMV auf $osname nicht vorgesehen (ohne-OMV-Pfad)"
fi

# 2) Bereits installiert (ArgonEON-Fall): Integration prüfen, nichts ändern
if omv_installed; then
    omvver=$(dpkg-query -W -f='${Version}' openmediavault 2>/dev/null || echo "?")
    ok "OpenMediaVault ist bereits installiert (Version $omvver)."
    mnt="${INSTALLER_MUSIC_MOUNT:-/mnt/music}"
    if findmnt "$mnt" >/dev/null 2>&1 || [[ -L "$mnt" ]]; then
        ok "$mnt ist eingebunden — Integration steht (disks-Modul hat verdrahtet)."
    else
        info "$mnt existiert noch nicht: In der OMV-UI den Musik-Share anlegen, danach"
        info "  bash install.sh --only disks   (setzt den Symlink + Schreibprobe)"
    fi
    info "Checkliste Musik-Share in OMV (Live-Lektion Phase 10):"
    info "  - Speicher → Dateisysteme: Datenplatte einbinden"
    info "  - Freigaben → Musik-Ordner auf der Platte, SMB aktivieren"
    info "  - Share-Zusatzoptionen: force user = ${SUDO_USER:-$(id -un)}"
    info "    (sonst darf Gast nicht in die vom Ingest angelegte Dropzone schreiben)"
    if have systemctl && sudocmd systemctl is-active smbd >/dev/null 2>&1; then
        ok "SMB-Dienst (smbd) läuft."
    else
        warn "smbd läuft nicht — SMB in der OMV-UI aktivieren."
    fi
    finish ok "OMV vorhanden, Integration geprüft"
fi

# 3) Frisch installieren — nur nach ausdrücklicher Entscheidung
if [[ "$(state_get ANSWER_disks_mode '')" == "OMV soll die Platten verwalten"* ]]; then
    do_install=yes   # Entscheidung fiel schon im disks-Modul (dort explizit gewählt)
    info "Platten-Modul hat OMV-Verwaltung bereits gewählt."
else
    warn "Das OMV-InstallScript übernimmt apt- und SSH-Konfiguration dieses Hosts"
    warn "und braucht 10–20 Minuten. SSH wird GEHÄRTET — ohne funktionierenden"
    warn "Key-Login als Sudo-User kann der Zugriff verloren gehen!"
    do_install=$(menu_select omv_install "OpenMediaVault jetzt installieren?" \
        "Nein — ohne OMV fortfahren (fstab + Samba-Modul)" \
        "Ja — OMV installieren (Debian, sauberes System)")
fi
case "$do_install" in
    "Ja"*) : ;;
    *)  info "Gut — ohne OMV: Platten per disks-Modul (fstab), Freigabe per samba-Modul."
        finish skip "OMV bewusst nicht installiert" ;;
esac

step "OMV-InstallScript läuft (10–20 Minuten, keine Panik bei Stille)"
if [[ ${INSTALLER_DRY_RUN:-0} == 1 ]]; then
    printf '    [dry-run] curl -fsSL %s -o /tmp/omv-install.sh\n' "$OMV_INSTALL_URL"
    printf '    [dry-run] bash /tmp/omv-install.sh\n'
    finish ok "dry-run: OMV-Installation nur angedeutet"
fi
curl -fsSL "$OMV_INSTALL_URL" -o /tmp/omv-install.sh \
    || finish fail "OMV-InstallScript nicht ladbar (Netz/GitHub erreichbar?)"
sudocmd bash /tmp/omv-install.sh \
    || finish fail "OMV-Installation fehlgeschlagen — Log des Scripts prüfen; Host ist unverändert nutzbar, --resume nach Analyse"

omv_installed || finish fail "InstallScript lief durch, aber openmediavault ist nicht installiert — Log prüfen"

ok "OMV installiert. Web-UI: http://$(hostname -I 2>/dev/null | awk '{print $1}') (admin/openmediavault — Passwort SOFORT ändern)"
info "Danach (UI): Dateisystem + Musik-Freigabe anlegen (force user = ${SUDO_USER:-$(id -un)}),"
info "dann die Integration verdrahten:"
info "  bash install.sh --only disks"
finish ok "OMV installiert; UI-Schritte offen (Share anlegen, dann --only disks)"
