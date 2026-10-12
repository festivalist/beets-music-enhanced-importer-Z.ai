#MODULE disks|Festplatten & Musik-Root (/mnt/music)|detect|0
# Bindet die Musik-Datenplatte(n) ein — auf zwei Wegen (Nutzerentscheidung
# 2026-10-12): direkt per fstab (ohne-OMV-Pfad, auch Ubuntu) oder als
# OMV-Integration (Platten verwaltet OMV selbst; hier passiert nur der
# /mnt/music-Symlink auf den Share — Phase-10-Konvention, hält beets-DB,
# config, Playlists und die compose-Staging-Mounts ohne Re-Home stabil).
#
# Schutzregeln („bricht nie halb kaputt ab“):
#   - Kandidaten sind nur ganze, NICHT eingehängte Datenplatten (die Root-
#     Platte hängt zwangsläufig irgendwo — sie fällt unter dieselbe Regel).
#   - Formatieren nur nach Identitätsanzeige (Modell/Serie/Größe/alter
#     Dateisystemtyp + Partitionen) und EINGETIPPTEM „JA“ — nie im State
#     speicherbar (confirm_destructive).
#   - fstab: Backup + Eintrag mit nofail + Probe-mountain; bei Fehler wird
#     das Backup zurückgespielt, bevor das Modul failed.
#   - 0 Platten ist OK: Modul überspringt sauber, später --add-disk.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$HERE/lib/common.sh"

MOUNT="${INSTALLER_MUSIC_MOUNT:-/mnt/music}"
FSTAB_PATH="${INSTALLER_FSTAB:-/etc/fstab}"   # Test-Harness-Override
RUN_USER="${SUDO_USER:-$(id -un)}"

# --- Helfer --------------------------------------------------------------------
omv_installed() {
    dpkg-query -W -f='${Status}' openmediavault 2>/dev/null | grep -q "install ok installed" \
        || have omv-confdb
}

disk_field() { # FIELD device → Wert (leer ok)
    lsblk -dn -o "$1" "$2" 2>/dev/null | head -1 | tr -d ' '
}

subtree_mounted() { # device → 0 wenn IRGENDWO im Subtree ein Mount/Swap hängt
    lsblk -nr -o MOUNTPOINTS "$1" 2>/dev/null | grep -q '[^[:space:]]'
}

list_candidates() { # füllt CAND_*-Arrays + druckt Tabelle; Echo = Anzahl
    CAND=(); CAND_SIZE=(); CAND_FSTYPE=(); CAND_LABEL=(); CAND_MODEL=(); CAND_SERIAL=()
    local name size type fstype label model serial
    while read -r name size type fstype label model serial; do
        [[ "$type" == "disk" ]] || continue
        [[ "$name" =~ ^(zram|ram|loop) ]] && continue
        [[ "$fstype" == "swap" ]] && continue
        subtree_mounted "/dev/$name" && continue   # Root-/System-/USB-Sticks hängen
        CAND+=("/dev/$name"); CAND_SIZE+=("$size"); CAND_FSTYPE+=("${fstype:-—}")
        CAND_LABEL+=("${label:---}"); CAND_MODEL+=("${model:-?}"); CAND_SERIAL+=("${serial:-?}")
    done < <(lsblk -dn -e 7 -o NAME,SIZE,TYPE,FSTYPE,LABEL,MODEL,SERIAL 2>/dev/null | awk '{print $1,$2,$3,$4,$5,$6,$7}')
    if [[ ${#CAND[@]} -eq 0 ]]; then
        info "Keine freien (nicht eingehängten) Datenplatten gefunden."
        return 0
    fi
    printf '    Nr  Gerät           Größe      Dateisystem  Label      Modell / Seriennummer\n'
    local i
    for i in "${!CAND[@]}"; do
        printf '    %2d  %-14s %-10s %-12s %-10s %s / %s\n' \
            $((i+1)) "${CAND[$i]##*/}" "${CAND_SIZE[$i]}" "${CAND_FSTYPE[$i]}" \
            "${CAND_LABEL[$i]}" "${CAND_MODEL[$i]}" "${CAND_SERIAL[$i]}"
    done
    return ${#CAND[@]}
}

identity_lines() { # device → mehrzeilige Identität für die Bestätigung
    local dev=$1
    printf 'Platte      : %s (%s)\n' "$dev" "$(disk_field SIZE "$dev")"
    printf 'Modell/Serie: %s / %s\n' "$(disk_field MODEL "$dev")" "$(disk_field SERIAL "$dev")"
    printf 'Alter Typ   : %s\n' "$(disk_field FSTYPE "$dev")"
    printf 'Partitionen : %s\n' "$(lsblk -n -o NAME "$dev" | tail -n +2 | tr '\n' ' ')"
}

sel_index_of() { # device → 1-basierte Nummer in CAND
    local i
    for i in "${!CAND[@]}"; do [[ "${CAND[$i]}" == "$1" ]] && echo $((i+1)) && return; done
    echo 0
}

select_disks() { # MAXN prompt-key "Frage" → SEL_DEVS[] (global, validiert+cachegespeichert)
    local maxn=$1 key=$2 prompt=$3 raw sel ok nums n dev
    raw=$(state_get "ANSWER_$key" "")
    if [[ -z "$raw" ]]; then
        if [[ ${INSTALLER_NONINTERACTIVE:-0} == 1 ]]; then
            raw="1"   # erste freie Platte — nur in Verbindung mit --force sinnvoll
            info "nicht-interaktiv: wähle Kandidat 1"
        else
            read -r -p "$prompt (z. B. 1 oder 1,2): " raw || raw=""
        fi
    fi
    while true; do
        ok=1; SEL_DEVS=()
        [[ "$raw" =~ ^[0-9]+([,.][0-9]+)*$ ]] || ok=0
        if [[ $ok == 1 ]]; then
            IFS=',.' read -ra nums <<< "$raw"
            if [[ ${#nums[@]} -gt $maxn ]]; then info "Maximal $maxn Platte(n) hier."; ok=0; fi
            for n in "${nums[@]}"; do
                n=$((10#$n))
                if [[ $n -ge 1 && $n -le ${#CAND[@]} ]]; then
                    dev="${CAND[$((n-1))]}"
                    # keine Dubletten
                    [[ " ${SEL_DEVS[*]-} " == *" $dev "* ]] || SEL_DEVS+=("$dev")
                else ok=0; fi
            done
        fi
        if [[ $ok == 1 && ${#SEL_DEVS[@]} -ge 1 ]]; then
            state_set "ANSWER_$key" "$raw"
            return 0
        fi
        if [[ ${INSTALLER_NONINTERACTIVE:-0} == 1 ]]; then
            err "Ungültige Auswahl '$raw' und nicht-interaktiv — Modul scheitert (kein Default möglich)."
            return 1
        fi
        raw=""
        read -r -p "Ungültige Auswahl — nochmal (Nummer(n), z. B. 1 oder 1,2): " raw || raw=""
    done
}

fstab_add_entry() { # "UUID=… /mount type opts dump pass" — Backup+Probe+Rollback
    local entry=$1 fstab="$FSTAB_PATH" bak
    if grep -q " $MOUNT " "$fstab" 2>/dev/null; then
        warn "fstab hat bereits einen Eintrag für $MOUNT — keiner wird hinzugefügt:"
        grep " $MOUNT " "$fstab" | sed 's/^/      /'
        return 0
    fi
    if [[ ${INSTALLER_DRY_RUN:-0} == 1 ]]; then
        printf '    [dry-run] fstab += %s\n' "$entry"
        return 0
    fi
    bak="$fstab.bak.$(date +%Y%m%d%H%M%S)"
    sudocmd cp "$fstab" "$bak"
    printf '%s\n' "$entry" | sudocmd tee -a "$fstab" >/dev/null
    if ! sudocmd mount -a; then
        err "Probe-Mount (mount -a) fehlgeschlagen — fstab wird zurückgespielt."
        sudocmd cp "$bak" "$fstab"
        sudocmd mount -a || true
        finish fail "fstab-Eintrag funktionierte nicht (Backup liegt neben der fstab)"
    fi
    ok "fstab-Eintrag aktiv (Backup: $bak)"
}

set_library_answer() { # /mnt/music als Bibliotheks-Default hinterlegen (nur wenn ungesetzt)
    if [[ -z "$(state_get ANSWER_library '')" ]]; then
        state_set ANSWER_library "$MOUNT"
        info "Bibliotheks-Default gesetzt: $MOUNT"
    fi
}

write_probe() { # Pfad → 0 wenn RUN_USER dort schreiben darf
    if [[ ${INSTALLER_DRY_RUN:-0} == 1 ]]; then
        printf '    [dry-run] Schreibprobe als %s in %s\n' "$RUN_USER" "$1"
        return 0
    fi
    as_user "$RUN_USER" touch "$1/.musik-installer-probe" 2>/dev/null \
        && rm -f "$1/.musik-installer-probe" 2>/dev/null \
        || { sudocmd rm -f "$1/.musik-installer-probe"; return 1; }
}

ensure_btrfs_tools() { # btrfs-progs nachinstallieren, falls gewählt/fehlt
    # btrfs-progs ist auf frischem Debian NICHT vorinstalliert — Live-Fund
    # der QEMU-Matrix 2026-10-12; das Paket bringt mkfs.btrfs UND btrfs CLI.
    have mkfs.btrfs && return 0
    run sudocmd apt-get update -qq || true
    run sudocmd apt-get install -y -qq btrfs-progs \
        || finish fail "btrfs-progs nicht installierbar — Repo/Netz prüfen, dann --resume"
}

# --- Add-Disk-Modus (--add-disk): Platte nachträglich -------------------------
if [[ ${INSTALLER_ADD_DISK:-0} == 1 ]]; then
    step "Festplatte nachträglich einbinden (--add-disk)"
    NCAND=0; list_candidates || NCAND=$?
    if [[ $NCAND -eq 0 ]]; then
        info "Keine freie Platte gefunden (belegte/eingehängte werden nie angefasst)."
        info "Nach dem Einbau:  bash install.sh --add-disk"
        finish skip "keine freie Platte vorhanden"
    fi
    MP_FSTYPE=$(findmnt -no FSTYPE "$MOUNT" 2>/dev/null || true)
    opts=("Neue Platte separat mounten (eigener Mountpoint)")
    [[ "$MP_FSTYPE" == "btrfs" ]] && opts+=("In Musik-btrfs-Pool aufnehmen (device add, Platz wächst sofort)")
    mode=$(menu_select adddisk_mode "Wie einbinden?" "${opts[@]}")
    case "$mode" in
        "Neue Platte separat mounten"*)
            target=$(ask_value adddisk_mount "Mountpoint" "/mnt/disk2")
            [[ "$target" == "/" || "$target" == "$MOUNT" ]] && finish fail "Mountpoint '$target' ist reserviert"
            select_disks 1 adddisk_sel "Welche Platte?" || finish fail "Auswahl fehlgeschlagen"
            dev="${SEL_DEVS[0]}"
            fs=$(menu_select adddisk_fs "Dateisystem" "btrfs" "ext4")
            confirm_destructive "Formatieren von $dev für separaten Mount $target" \
                || finish skip "nicht bestätigt — nichts passiert"
            ensure_btrfs_tools
            run sudocmd wipefs -a "$dev"
            if [[ "$fs" == btrfs* ]]; then run sudocmd mkfs.btrfs -L musik2 "$dev"
            else run sudocmd mkfs.ext4 -L musik2 "$dev"; fi
            uuid=$(blkid -s UUID -o value "$dev")
            if [[ -z "$uuid" && ${INSTALLER_DRY_RUN:-0} == 1 ]]; then uuid="DRYRUN-UUID"; fi
            [[ -n "$uuid" ]] || finish fail "keine UUID nach Formatierung ($dev)"
            run sudocmd mkdir -p "$target"
            pass=0; [[ "$fs" != btrfs* ]] && pass=2
            fstab_add_entry "UUID=$uuid $target $fs defaults,nofail 0 $pass"
            run sudocmd mount "$target" 2>/dev/null || run sudocmd mount -a
            run sudocmd chown "$RUN_USER:$RUN_USER" "$target"
            finish ok "$dev → $target ($fs)" ;;
        *)
            select_disks 1 adddisk_sel "Welche Platte in den Pool?" || finish fail "Auswahl fehlgeschlagen"
            dev="${SEL_DEVS[0]}"
            confirm_destructive "Formatieren von $dev und Aufnahme in den btrfs-Pool $MOUNT" \
                || finish skip "nicht bestätigt — nichts passiert"
            ensure_btrfs_tools
            run sudocmd wipefs -a "$dev"
            run sudocmd btrfs device add "$dev" "$MOUNT" \
                || finish fail "btrfs device add fehlgeschlagen (btrfs-progs installiert?)"
            info "Platz ist sofort nutzbar. Vorhandene Daten optional umverteilen (Dauer!):"
            info "  sudo btrfs balance start -dusage=50 -musage=50 $MOUNT"
            finish ok "$dev in btrfs-Pool aufgenommen" ;;
    esac
fi

# --- Normalmodus ---------------------------------------------------------------
step "Festplatten & Musik-Root ($MOUNT)"

# 1) Idempotenz: schon eingebunden (Mount oder Symlink)?
if findmnt "$MOUNT" >/dev/null 2>&1; then
    ok "$MOUNT ist bereits eingebunden: $(findmnt -no SOURCE,FSTYPE "$MOUNT" | tr '\n' ' ')"
    set_library_answer
    finish ok "$MOUNT bereits gemountet"
fi
if [[ -L "$MOUNT" ]]; then
    target=$(readlink -f "$MOUNT")
    if [[ -d "$target" ]] && write_probe "$target"; then
        ok "$MOUNT ist ein Symlink auf $target (beschreibbar)"
        set_library_answer
        finish ok "Symlink auf $target"
    fi
    err "$MOUNT ist ein Symlink auf '$target', aber Ziel fehlt oder nicht schreibbar."
    finish fail "toter Symlink $MOUNT — auflösen oder Ziel prüfen"
fi

# 2) OMV bereits installiert (ArgonEON-Fall): Platten macht OMV, hier nur
#    die Integration — Share finden, Symlink setzen, Schreibrechte prüfen.
if omv_installed; then
    info "OpenMediaVault ist installiert — Platten/Shares verwaltet OMV (UI)."
    mapfile -t SHARES < <(find /srv -maxdepth 3 -type d \( -iname "musik" -o -iname "music" \) 2>/dev/null | head -5)
    if [[ ${#SHARES[@]} -eq 0 ]]; then
        info "Kein Musik-Share unter /srv gefunden."
        info "In der OMV-UI: Speicher → Freigaben → Musik-Ordner auf der Datenplat anlegen,"
        info "danach:  bash install.sh --only disks   (setzt den $MOUNT-Symlink)"
        finish skip "OMV da, aber noch kein Musik-Share — UI-Schritt, danach --only disks"
    fi
    share=$(menu_select omv_share "Welcher Share ist die Musikbibliothek?" "${SHARES[@]}")
    if ! write_probe "$share"; then
        warn "Schreibprobe als $RUN_USER in $share fehlgeschlagen — Rechte in OMV prüfen"
        warn "(SMB-Share: force user = $RUN_USER; Dateisystem: Besitzer anpassen)."
    fi
    run sudocmd ln -sfn "$share" "$MOUNT"
    ok "$MOUNT → $share"
    set_library_answer
    finish ok "OMV-Share $share verlinkt"
fi

# 3) Strategie: fstab direkt | OMV später | jetzt ohne Platte
opts=("Festplatte jetzt direkt einbinden (fstab — auch der Ubuntu-Weg)")
if [[ "$(state_get ANSWER_omv_supported 0)" == "1" ]]; then
    opts+=("OMV soll die Platten verwalten (Debian; Installation folgt im OMV-Modul)")
fi
opts+=("Jetzt ohne eigene Musik-Platte fortfahren (später per --add-disk)")
mode=$(menu_select disks_mode "Wie soll die Musik-Platte eingebunden werden?" "${opts[@]}")
case "$mode" in
    "Festplatte jetzt direkt einbinden"*) : ;;
    "OMV soll"*)
        info "Gut — das Platten-Modul tritt zurück; OMV (Modul 30) installiert und"
        info "führt. Nach dem Anlegen des Musik-Shares in der OMV-UI:"
        info "  bash install.sh --only disks    (setzt den $MOUNT-Symlink)"
        finish skip "Plattenverwaltung an OMV übergeben" ;;
    *)
        info "Ohne Musik-Platte: Der Setup-Wizard fragt dann einen Bibliotheksordner ab"
        info "(Default ~/Music). Platte später einbauen und:  bash install.sh --add-disk"
        finish skip "bewusst ohne Musik-Platte (Bibliothek z. B. unter ~/Music)" ;;
esac

# 4) Platte(n) wählen
NCAND=0; list_candidates || NCAND=$?
if [[ $NCAND -eq 0 ]]; then
    info "Keine freie Datenplatte gefunden — belegte Platten (inkl. Systemplatte)"
    info "werden vom Installer nie angefasst."
    info "Platte später einbauen und:  bash install.sh --add-disk"
    finish skip "keine freie Platte — später --add-disk"
fi
select_disks 2 disks_selected "Welche Platte(n) für die Musikbibliothek?" \
    || finish fail "Plattenauswahl fehlgeschlagen"

# 5) Dateisystem
if [[ ${#SEL_DEVS[@]} -eq 1 ]]; then
    fs=$(menu_select disks_fs "Dateisystem" "btrfs" "ext4")
else
    fs=$(menu_select disks_fs "Dateisystem (mehrere Platten → btrfs)" "btrfs")
fi
if [[ "$fs" == btrfs* && ${#SEL_DEVS[@]} -ge 2 ]]; then
    profile=$(menu_select disks_profile "btrfs-Datenprofil" \
        "single (volle Kapazität, keine Redundanz)" \
        "raid1 (gespiegelt, halbe Kapazität)")
else
    profile="single"
fi

# 6) Identität zeigen + destruktive Bestätigung (nie cachebar)
step "Formatieren — letzte Sicherheit"
for dev in "${SEL_DEVS[@]}"; do identity_lines "$dev"; done
[[ "$fs" == btrfs* ]] && tname=btrfs || tname=ext4
devlist="${SEL_DEVS[*]}"
confirm_destructive "Formatieren von $devlist als $tname (Musik-Root $MOUNT)" \
    || finish skip "nicht bestätigt — nichts wurde verändert"

# 7) Formatieren + Mount + fstab
ensure_btrfs_tools
run sudocmd wipefs -a "${SEL_DEVS[@]}"
if [[ "$fs" == btrfs* ]]; then
    if [[ ${#SEL_DEVS[@]} -eq 1 ]]; then
        run sudocmd mkfs.btrfs -L musik "${SEL_DEVS[@]}"
    elif [[ "$profile" == raid1* ]]; then
        run sudocmd mkfs.btrfs -L musik -d raid1 -m raid1 "${SEL_DEVS[@]}"
    else
        run sudocmd mkfs.btrfs -L musik -d single -m raid1 "${SEL_DEVS[@]}"
    fi
else
    run sudocmd mkfs.ext4 -L musik "${SEL_DEVS[@]}"
fi
uuid=$(blkid -s UUID -o value "${SEL_DEVS[0]}")
if [[ -z "$uuid" && ${INSTALLER_DRY_RUN:-0} == 1 ]]; then uuid="DRYRUN-UUID"; fi
[[ -n "$uuid" ]] || finish fail "keine UUID nach Formatierung (${SEL_DEVS[0]})"
run sudocmd mkdir -p "$MOUNT"
pass=0; [[ "$fs" != btrfs* ]] && pass=2
fstab_add_entry "UUID=$uuid $MOUNT $tname defaults,nofail 0 $pass"
run sudocmd mount "$MOUNT" 2>/dev/null || run sudocmd mount -a
run sudocmd chown "$RUN_USER:$RUN_USER" "$MOUNT"

if ! write_probe "$MOUNT"; then
    warn "Schreibprobe fehlgeschlagen — Rechte von $MOUNT manuell prüfen (chown $RUN_USER)."
fi
set_library_answer
ok "Musik-Root: $MOUNT ($tname, $devlist)"
finish ok "$MOUNT auf $devlist ($tname) eingebunden"
