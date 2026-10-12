#!/usr/bin/env bash
# harness_disks.sh — Mock-Harness für install.d/20-disks.sh (Story 8.2).
# Läuft überall dort, wo Bash existiert (auch Git Bash auf Windows), und
# berührt NICS Systemnahes: lsblk/findmnt/blkid/sudo/mount/… sind Mocks,
# fstab + Musik-Mount liegen im Temp-Verzeichnis. Die echte Matrix gegen
# Debian/Ubuntu-VMs macht Story 8.7 (QEMU) — hier wird die Logik geprüft:
# Kandidatenfilter (Root-Platte raus), Bestätigungs-Gate, fstab-Eintrag,
# Idempotenz, OMV-Erkennung, --add-Disk (separat + btrfs-Pool).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT=$(mktemp -d "${TMPDIR:-/tmp}/musik-disk-harness.XXXXXX")
trap 'echo "Harness-Verzeichnis: $ROOT"' EXIT

mkdir -p "$ROOT/fakebin" "$ROOT/mods/lib" "$ROOT/state" "$ROOT/mnt-music" "$ROOT/srv-fake"
cp "$REPO/install.d/lib/common.sh" "$ROOT/mods/lib/"
cp "$REPO/install.d/20-disks.sh" "$ROOT/mods/"
export MUSIC_MOUNT="$ROOT/mnt-music"

# --- Mocks ---------------------------------------------------------------------
cat > "$ROOT/fakebin/lsblk" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  "-dn -e 7 -o NAME,SIZE,TYPE,FSTYPE,LABEL,MODEL,SERIAL")
    echo "sda 100G disk - - FakeRoot ROOTSER"
    echo "sdb 16.4T disk - - FakeDiskOne SER111"
    echo "sdc 16.4T disk ext4 MusikAlt FakeDiskTwo SER222"
    echo "sdd 500G disk - - FakeDiskThree SER333" ;;
  "-nr -o MOUNTPOINTS /dev/sda") echo "/ /boot" ;;
  "-nr -o MOUNTPOINTS /dev/sdb"|"-nr -o MOUNTPOINTS /dev/sdc"|"-nr -o MOUNTPOINTS /dev/sdd") : ;;
  "-dn -o SIZE /dev/sdb"|"-dn -o SIZE /dev/sdc") echo "16.4T" ;;
  "-dn -o SIZE /dev/sdd") echo "500G" ;;
  "-dn -o MODEL /dev/sdb") echo "FakeDiskOne" ;;
  "-dn -o MODEL /dev/sdc") echo "FakeDiskTwo" ;;
  "-dn -o MODEL /dev/sdd") echo "FakeDiskThree" ;;
  "-dn -o SERIAL /dev/sdb") echo "SER111" ;;
  "-dn -o SERIAL /dev/sdc") echo "SER222" ;;
  "-dn -o SERIAL /dev/sdd") echo "SER333" ;;
  "-dn -o FSTYPE /dev/sdb"|"-dn -o FSTYPE /dev/sdd") : ;;
  "-dn -o FSTYPE /dev/sdc") echo "ext4" ;;
  "-n -o NAME /dev/sdb"|"-n -o NAME /dev/sdc"|"-n -o NAME /dev/sdd") echo "${3##*/}" ;;
  *) echo "LSBLK-MOCK: unerwartete Argumente: $*" >&2; exit 1 ;;
esac
EOF
cat > "$ROOT/fakebin/findmnt" <<EOF
#!/usr/bin/env bash
if [[ "\$1" == "-no" && "\${MOCK_MUSIC_MOUNTED:-0}" == 1 && "\$3" == "\$MUSIC_MOUNT" ]]; then
  [[ "\$2" == FSTYPE ]] && echo btrfs || echo "/dev/sdb btrfs"; exit 0
fi
if [[ "\$1" == "\$MUSIC_MOUNT" && "\${MOCK_MUSIC_MOUNTED:-0}" == 1 ]]; then exit 0; fi
exit 1
EOF
cat > "$ROOT/fakebin/blkid" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "-s" ]] || exit 1
dev="${@: -1}"
echo "TEST-UUID-${dev##*/}"
EOF
for m in wipefs mkfs.btrfs mkfs.ext4 btrfs mount chown; do
  printf '#!/usr/bin/env bash\necho "MOCK %s: $*" >> "$MOCKDIR/mock.log"\nexit 0\n' "$m" > "$ROOT/fakebin/$m"
done
cat > "$ROOT/fakebin/sudo" <<'EOF'
#!/usr/bin/env bash
echo "SUDO: $*" >> "$MOCKDIR/mock.log"
[[ "$1" == "-u" ]] && shift 2
"$@"
EOF
printf '#!/usr/bin/env bash\n[[ ${MOCK_OMV:-0} == 1 ]] && echo "install ok installed" && exit 0\nexit 1\n' > "$ROOT/fakebin/dpkg-query"
chmod +x "$ROOT"/fakebin/*
export MOCKDIR="$ROOT" PATH="$ROOT/fakebin:$PATH"

PASS=0; FAIL=0
check() { # Name Bedingung(shell) — Bedingung wird per bash -c geprüft
    if eval "$2"; then printf '  PASS %s\n' "$1"; PASS=$((PASS+1))
    else printf '  FAIL %s   [%s]\n' "$1" "$2"; FAIL=$((FAIL+1)); fi
}
run_installer() { # extra-args…
    MUSIK_INSTALLER_TEST=1 MUSIK_INSTALLER_STATE="$ROOT/state" \
    MUSIK_INSTALLER_MODULES="$ROOT/mods" INSTALLER_MUSIC_MOUNT="$MUSIC_MOUNT" \
    INSTALLER_FSTAB="$ROOT/fstab" bash "$REPO/install.sh" --only disks \
       --non-interactive --force "$@" 2>&1
}
reset_state() { rm -rf "$ROOT/state"; mkdir -p "$ROOT/state"; echo "MOD_detect=ok" > "$ROOT/state/state.env"; : > "$ROOT/fstab"; : > "$ROOT/mock.log"; }

# --- Szenario 1: Normaler fstab-Lauf formatiert Kandidat 1, fstab-Eintrag ------
echo "== Szenario 1: direkter fstab-Lauf (btrfs, Kandidat 1 = sdb) =="
reset_state
rc=0; out=$(run_installer) || rc=$?
check "Lauf erfolgreich (exit 0)"            "[[ $rc -eq 0 ]]"
echo "$out" | tail -5
check "Modulstatus ok"                       "grep -q '^MOD_disks=ok$' '$ROOT/state/state.env'"
check "wipefs auf sdb gerufen"               "grep -q 'wipefs: -a /dev/sdb' '$ROOT/mock.log'"
check "mkfs.btrfs auf sdb"                   "grep -q 'mkfs.btrfs: -L musik /dev/sdb' '$ROOT/mock.log'"
check "Root-Platte sda NIE angefasst"        "! grep -q 'sda' '$ROOT/mock.log'"
check "fstab-Eintrag mit UUID+nofail"        "grep -q 'UUID=TEST-UUID-sdb $MUSIC_MOUNT btrfs defaults,nofail 0 0' '$ROOT/fstab'"
check "fstab-Backup erstellt"                "ls '$ROOT'/fstab.bak.* >/dev/null 2>&1"
check "Bibliotheks-Default gesetzt"          "grep -q '^ANSWER_library=$MUSIC_MOUNT' '$ROOT/state/state.env'"

# --- Szenario 2: Idempotenz — /mnt/music hängt schon → kein mkfs ---------------
echo "== Szenario 2: bereits gemountet → kein Formatieren =="
reset_state; export MOCK_MUSIC_MOUNTED=1
out=$(run_installer || true)
check "Modulstatus ok"                       "grep -q '^MOD_disks=ok$' '$ROOT/state/state.env'"
check "kein wipefs/mkfs"                     "! grep -Eq 'wipefs|mkfs' '$ROOT/mock.log'"
check "Meldung 'bereits'"                    "echo \"\$out\" | grep -q 'bereits'"
unset MOCK_MUSIC_MOUNTED

# --- Szenario 3: OMV installiert, kein Share → sauberer Skip mit UI-Hinweis ---
echo "== Szenario 3: OMV da, kein Musik-Share =="
reset_state; export MOCK_OMV=1
out=$(run_installer || true)
check "Modulstatus skip"                     "grep -q '^MOD_disks=skip$' '$ROOT/state/state.env'"
check "UI-Hinweis enthalten"                 "echo \"\$out\" | grep -q 'OMV-UI'"
check "nichts formatiert"                    "! grep -Eq 'wipefs|mkfs' '$ROOT/mock.log'"
unset MOCK_OMV

# --- Szenario 4: --add-disk separat (eigener Mountpoint) -----------------------
echo "== Szenario 4: --add-disk, separates Mounten =="
reset_state
printf 'ANSWER_adddisk_mount=%s\n' "$ROOT/disk2" > "$ROOT/answers.env"
out=$(run_installer --add-disk --answers "$ROOT/answers.env" || true)
check "Modulstatus ok"                       "grep -q '^MOD_disks=ok$' '$ROOT/state/state.env'"
check "mkfs für separaten Mount"             "grep -q 'mkfs.btrfs: -L musik2 /dev/sdb' '$ROOT/mock.log'"
check "fstab-Eintrag disk2"                  "grep -q 'UUID=TEST-UUID-sdb $ROOT/disk2 btrfs defaults,nofail 0 0' '$ROOT/fstab'"

# --- Szenario 5: --add-disk in btrfs-Pool (device add, kein mkfs) --------------
echo "== Szenario 5: --add-disk, btrfs device add =="
reset_state; export MOCK_MUSIC_MOUNTED=1
printf 'ANSWER_adddisk_mode=%s\n' "In Musik-btrfs-Pool aufnehmen (device add, Platz wächst sofort)" > "$ROOT/answers.env"
out=$(run_installer --add-disk --answers "$ROOT/answers.env" || true)
check "Modulstatus ok"                       "grep -q '^MOD_disks=ok$' '$ROOT/state/state.env'"
check "btrfs device add gerufen"             "grep -q 'btrfs: device add /dev/sdb $MUSIC_MOUNT' '$ROOT/mock.log'"
check "kein mkfs im Pool-Pfad"               "! grep -q 'mkfs' '$ROOT/mock.log'"
unset MOCK_MUSIC_MOUNTED

# --- Szenario 6: ohne --force verweigert destruktiv (non-interactive) ----------
echo "== Szenario 6: destruktiv ohne --force → sauberer SKIP, nichts passiert =="
reset_state
out=$(MUSIK_INSTALLER_TEST=1 MUSIK_INSTALLER_STATE="$ROOT/state" \
     MUSIK_INSTALLER_MODULES="$ROOT/mods" INSTALLER_MUSIC_MOUNT="$MUSIC_MOUNT" \
     INSTALLER_FSTAB="$ROOT/fstab" bash "$REPO/install.sh" --only disks --non-interactive 2>&1) \
     || true
check "Modulstatus skip (nicht fail)"        "grep -q '^MOD_disks=skip$' '$ROOT/state/state.env'"
check "nichts formatiert"                    "! grep -Eq 'wipefs|mkfs' '$ROOT/mock.log'"
check "Hinweis auf --force"                  "echo \"\$out\" | grep -q -- '--force'"

echo
echo "================ ERGEBNIS: $PASS bestanden, $FAIL fehlgeschlagen ==============="
[[ $FAIL -eq 0 ]]
