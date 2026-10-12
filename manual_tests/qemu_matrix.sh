#!/usr/bin/env bash
# qemu_matrix.sh — EPIC 8 Story 8.7: reale OS-Testmatrix für den One-Shot-
# Installer, lauffähig auf dem Windows-PC (Git Bash + scoop-QEMU, kein Admin).
#
# Was hier passiert:
#   - Debian 12 (bookworm) und Ubuntu 24.04 (noble) als QEMU-Cloud-VMs
#   - Cloud-init-NoCloud-Seed per SMBIOS-serial + lokalem HTTP-Server
#     (10.0.2.2 = Host aus der SLIRP-Perspektive)
#   - je 1–2 virtuelle 8-GB-Datenplatten (raw) als echte mkfs/mount/fstab-
#     Kandidaten; SSH-Forward 2222 (Debian) / 2223 (Ubuntu), Key in tools/qemu
#   - Repo wird IN der VM von GitHub geklont (testet den gepushten Stand)
#
# Szenarien (in run_matrix): detect/disks/base/musik echt, Resume-Idempotenz,
# --add-disk, docker, plex (Debian), OMV-Ablehnung auf Ubuntu, verify.
# Voraussetzung: scoop install qemu (oder qemu im PATH) + Repo-.venv (für den
# Seed-HTTP-Server). Images liegen unter tools/qemu/images (gitignored).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QDIR="$REPO/tools/qemu"
QEMU="${QEMU:-$(ls "$HOME/scoop/apps/qemu/current/qemu-system-x86_64.exe" 2>/dev/null || command -v qemu-system-x86_64 || true)}"
QIMG="${QIMG:-$(ls "$HOME/scoop/apps/qemu/current/qemu-img.exe" 2>/dev/null || command -v qemu-img || true)}"
PY="$REPO/.venv/Scripts/python.exe"; [[ -x "$PY" ]] || PY="$REPO/.venv/bin/python"
SSH_OPTS=(-i "$QDIR/id_test" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8)
DEB_URL="https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2"
UBU_URL="https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
[[ -n "$QEMU" && -n "$QIMG" ]] || { echo "QEMU fehlt: scoop install qemu"; exit 1; }

vm_ssh() { local port=$1; shift; ssh "${SSH_OPTS[@]}" -p "$port" tester@localhost "$@"; }
vm_alive() { local port=$1; vm_ssh "$port" 'echo ok' >/dev/null 2>&1; }

cmd_setup() {          # Einmalig: Key, Seeds, Images
    mkdir -p "$QDIR/images" "$QDIR/seed/debian" "$QDIR/ubuntu" "$QDIR/run" 2>/dev/null || true
    mkdir -p "$QDIR/seed/ubuntu"
    [[ -f "$QDIR/id_test" ]] || ssh-keygen -q -t ed25519 -N "" -C musik-qemu-test -f "$QDIR/id_test"
    local pub; pub=$(cat "$QDIR/id_test.pub")
    local d hn
    for d in debian ubuntu; do
        hn=musik-deb; [[ $d == ubuntu ]] && hn=musik-ubu
        cat > "$QDIR/seed/$d/user-data" <<EOF
#cloud-config
hostname: $hn
ssh_pwauth: false
users:
  - name: tester
    sudo: ALL=(ALL) NOPASSWD:ALL
    groups: sudo
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys:
      - $pub
runcmd:
  - [ systemctl, enable, --now, ssh ]
  - [ sh, -c, 'touch /tmp/cloud-ready' ]
EOF
        printf 'instance-id: musik-%s-1\nlocal-hostname: %s\n' "$d" "$hn" > "$QDIR/seed/$d/meta-data"
    done
    [[ -f "$QDIR/images/debian12.qcow2" ]] || curl -sL -o "$QDIR/images/debian12.qcow2" "$DEB_URL"
    [[ -f "$QDIR/images/ubuntu2404.img"  ]] || curl -sL -o "$QDIR/images/ubuntu2404.img" "$UBU_URL"
    echo "Setup ok: $(du -sh "$QDIR/images" | cut -f1) Images, Seeds, Key"
}

seed_server_start() {
    if ! curl -fsS -o /dev/null http://127.0.0.1:8000/debian/user-data 2>/dev/null; then
        ( "$PY" -m http.server 8000 --bind 127.0.0.1 --directory "$QDIR/seed" >/dev/null 2>&1 & )
        sleep 2
    fi
    curl -fsS -o /dev/null http://127.0.0.1:8000/debian/user-data || { echo "Seed-Server startet nicht"; exit 1; }
}

cmd_boot() {           # boot [debian|ubuntu|both]
    local which=${1:-both}
    seed_server_start
    cd "$REPO"
    if [[ $which == debian || $which == both ]]; then
        [[ -f tools/qemu/run/deb-run.qcow2 ]] || "$QIMG" create -f qcow2 -F qcow2 \
            -b "$(pwd -W 2>/dev/null || pwd)/tools/qemu/images/debian12.qcow2" tools/qemu/run/deb-run.qcow2 >/dev/null
        [[ -f tools/qemu/run/data1.raw ]] || "$QIMG" create -f raw tools/qemu/run/data1.raw 8G >/dev/null
        [[ -f tools/qemu/run/data2.raw ]] || "$QIMG" create -f raw tools/qemu/run/data2.raw 8G >/dev/null
        "$QEMU" -machine q35 -accel tcg,thread=multi -cpu max -smp 4 -m 3072 \
          -drive file=tools/qemu/run/deb-run.qcow2,if=virtio,format=qcow2 \
          -drive file=tools/qemu/run/data1.raw,if=virtio,format=raw \
          -drive file=tools/qemu/run/data2.raw,if=virtio,format=raw \
          -netdev user,id=n0,hostfwd=tcp:127.0.0.1:2222-:22 -device virtio-net-pci,netdev=n0 \
          -smbios "type=1,serial=ds=nocloud-net;s=http://10.0.2.2:8000/debian/" \
          -display none -serial file:tools/qemu/run/console-deb.log >/dev/null 2>&1 &
        echo "Debian-VM startet (SSH: Port 2222)"
    fi
    if [[ $which == ubuntu || $which == both ]]; then
        [[ -f tools/qemu/run/ubu-run.qcow2 ]] || "$QIMG" create -f qcow2 -F qcow2 \
            -b "$(pwd -W 2>/dev/null || pwd)/tools/qemu/images/ubuntu2404.img" tools/qemu/run/ubu-run.qcow2 >/dev/null
        [[ -f tools/qemu/run/data3.raw ]] || "$QIMG" create -f raw tools/qemu/run/data3.raw 8G >/dev/null
        "$QEMU" -machine q35 -accel tcg,thread=multi -cpu max -smp 4 -m 3072 \
          -drive file=tools/qemu/run/ubu-run.qcow2,if=virtio,format=qcow2 \
          -drive file=tools/qemu/run/data3.raw,if=virtio,format=raw \
          -netdev user,id=n0,hostfwd=tcp:127.0.0.1:2223-:22 -device virtio-net-pci,netdev=n0 \
          -smbios "type=1,serial=ds=nocloud-net;s=http://10.0.2.2:8000/ubuntu/" \
          -display none -serial file:tools/qemu/run/console-ubu.log >/dev/null 2>&1 &
        echo "Ubuntu-VM startet (SSH: Port 2223)"
    fi
}

wait_ssh() { local port=$1 name=$2 i
    for i in $(seq 1 30); do
        vm_alive "$port" && { echo "$name: SSH bereit"; return 0; }
        sleep 10
    done
    echo "$name: TIMEOUT"; return 1
}

vm_prepare() {         # Repo von GitHub klonen (testet den gepushten Stand)
    local port=$1
    vm_ssh "$port" 'sudo apt-get update -qq >/dev/null 2>&1; sudo apt-get install -y -qq git >/dev/null 2>&1; rm -rf ~/musik; git clone -q https://github.com/festivalist/beets-music-enhanced-importer-Z.ai.git ~/musik && cd ~/musik && git log --oneline -1'
}

# --- Szenario-Funktionen (in der VM ausgeführt) -----------------------------------
scen_disks_btrfs() { vm_ssh "$1" 'cd ~/musik && bash install.sh --only detect --non-interactive >/dev/null 2>&1; bash install.sh --only disks --non-interactive --force 2>&1 | tail -3; findmnt -no FSTYPE,SOURCE /mnt/music && grep -c "/mnt/music" /etc/fstab'; }
scen_core() { vm_ssh "$1" 'cd ~/musik && bash install.sh --only base,musik --non-interactive 2>&1 | tail -3; .venv/bin/python musik.py fetch --self-test >/dev/null 2>&1 && echo SELFTEST-OK; systemctl is-enabled musik-bot.service musik-ingest.timer'; }
scen_resume() { vm_ssh "$1" 'cd ~/musik && bash install.sh --core-only --non-interactive 2>&1 | grep -c "bereits erledigt"'; }
scen_add_disk() { vm_ssh "$1" 'cd ~/musik && printf "ANSWER_adddisk_mount=/mnt/disk2\n" > /tmp/ans.env && bash install.sh --add-disk --answers /tmp/ans.env --non-interactive --force 2>&1 | tail -2; findmnt -no FSTYPE,SOURCE /mnt/disk2 && grep -c "/mnt/disk2" /etc/fstab'; }
scen_docker() { vm_ssh "$1" 'cd ~/musik && bash install.sh --only docker --non-interactive 2>&1 | tail -2; sudo docker compose version'; }
scen_plex() { vm_ssh "$1" 'cd ~/musik && bash install.sh --only plex --non-interactive 2>&1 | grep -E "installiert|geclaimt" | head -3; dpkg-query -W -f="\${Status}\n" plexmediaserver'; }
scen_omv_ubuntu() { vm_ssh "$1" 'cd ~/musik && bash install.sh --only detect,omv --non-interactive 2>&1 | grep -E "nicht vorgesehen|ohne-OMV" | head -2'; }
scen_verify() { vm_ssh "$1" 'cd ~/musik && bash install.sh --only verify --non-interactive 2>&1 | grep -E "^  [✓✗—]" '; }

cmd_run() {            # run [debian|ubuntu|both]
    local which=${1:-both}
    PASS=0; FAIL=0
    check() { if eval "$2"; then printf '  PASS %s\n' "$1"; PASS=$((PASS+1))
              else printf '  FAIL %s\n' "$1"; FAIL=$((FAIL+1)); fi; }
    if [[ $which == debian || $which == both ]]; then
        echo "== Debian 12 (Port 2222) =="
        vm_alive 2222 || { wait_ssh 2222 Debian; vm_prepare 2222; }
        out=$(scen_disks_btrfs 2222)   || true
        check "disks: /mnt/music btrfs + fstab"   "echo \"\$out\" | grep -q btrfs && echo \"\$out\" | grep -q vdb"
        out=$(scen_core 2222)          || true
        check "musik: self-test + Units"          "echo \"\$out\" | grep -q SELFTEST-OK && echo \"\$out\" | grep -q enabled"
        out=$(scen_resume 2222)        || true
        check "resume: alles bereits erledigt"    "[[ \$(echo \"\$out\" | tail -1) -ge 3 ]]"
        out=$(scen_add_disk 2222)      || true
        check "add-disk: /mnt/disk2 + fstab"      "echo \"\$out\" | grep -q disk2"
        out=$(scen_docker 2222)        || true
        check "docker: compose v2 läuft"          "echo \"\$out\" | grep -q 'Compose version'"
        out=$(scen_plex 2222)          || true
        check "plex: installiert, Claim ausstehend" "echo \"\$out\" | grep -q 'install ok installed'"
        out=$(scen_verify 2222)        || true
        check "verify: Report-Karte"              "echo \"\$out\" | grep -q 'Musik-Root'"
    fi
    if [[ $which == ubuntu || $which == both ]]; then
        echo "== Ubuntu 24.04 (Port 2223) =="
        vm_alive 2223 || { wait_ssh 2223 Ubuntu; vm_prepare 2223; }
        out=$(scen_disks_btrfs 2223)   || true
        check "disks: /mnt/music btrfs + fstab"   "echo \"\$out\" | grep -q btrfs && echo \"\$out\" | grep -q vdc"
        out=$(scen_omv_ubuntu 2223)    || true
        check "omv: ehrliche Ablehnung auf Ubuntu" "echo \"\$out\" | grep -q 'nicht vorgesehen'"
        out=$(scen_core 2223)          || true
        check "musik: self-test + Units"          "echo \"\$out\" | grep -q SELFTEST-OK"
        out=$(scen_docker 2223)        || true
        check "docker: compose v2 läuft"          "echo \"\$out\" | grep -q 'Compose version'"
        out=$(scen_verify 2223)        || true
        check "verify: Report-Karte"              "echo \"\$out\" | grep -q 'Musik-Root'"
    fi
    echo "================ ERGEBNIS: $PASS bestanden, $FAIL fehlgeschlagen ==============="
    [[ $FAIL -eq 0 ]]
}

cmd_cleanup() {        # VMs stoppen (qemu-Prozesse), Disks behalten
    powershell.exe -NoProfile -Command "Get-Process qemu-system-x86_64 -ErrorAction SilentlyContinue | Stop-Process -Force" >/dev/null 2>&1 || true
    echo "VMs gestoppt. Images/Disks unter tools/qemu/run bleiben (loeschen fuer frischen Start)."
}

case "${1:-}" in
    setup)  cmd_setup ;;
    boot)   cmd_boot "${2:-both}" ;;
    run)    cmd_run "${2:-both}" ;;
    stop)   cmd_cleanup ;;
    all)    cmd_setup; cmd_boot both; wait_ssh 2222 Debian; vm_prepare 2222
            wait_ssh 2223 Ubuntu 2>/dev/null || true; vm_prepare 2223 2>/dev/null || true
            cmd_run both ;;
    *) echo "Usage: bash manual_tests/qemu_matrix.sh setup|boot|run|stop|all [debian|ubuntu|both]"; exit 1 ;;
esac
