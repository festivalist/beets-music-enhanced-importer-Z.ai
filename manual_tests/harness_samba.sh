#!/usr/bin/env bash
# harness_samba.sh — Logik-Tests für install.d/32-samba.sh und den
# Ubuntu-Skip von 30-omv.sh (Story 8.3). Mocks statt Systemeingriffe;
# smb.conf liegt im Temp-Verzeichnis (INSTALLER_SMBCONF-Override).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT=$(mktemp -d "${TMPDIR:-/tmp}/musik-samba-harness.XXXXXX")
trap 'echo "Harness-Verzeichnis: $ROOT"' EXIT
mkdir -p "$ROOT/fakebin" "$ROOT/mods/lib" "$ROOT/state" "$ROOT/lib-music"
cp "$REPO/install.d/lib/common.sh" "$ROOT/mods/lib/"
cp "$REPO/install.d/32-samba.sh" "$REPO/install.d/30-omv.sh" "$ROOT/mods/"

cat > "$ROOT/fakebin/dpkg-query" <<'EOF'
#!/usr/bin/env bash
pkg="${@: -1}"
case " ${MOCK_PKGS:-} " in
  *" $pkg "*) echo "install ok installed"; exit 0 ;;
esac
exit 1
EOF
cat > "$ROOT/fakebin/systemctl" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "is-active" ]] && { echo active; exit 0; }
exit 0
EOF
printf '#!/usr/bin/env bash\necho "LISTEN 0 128 0.0.0.0:445 0.0.0.0:*"\n' > "$ROOT/fakebin/ss"
cat > "$ROOT/fakebin/sudo" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "-u" ]] && shift 2
"$@"
EOF
for m in apt-get; do printf '#!/usr/bin/env bash\nexit 0\n' > "$ROOT/fakebin/$m"; done
chmod +x "$ROOT"/fakebin/*
export MOCKDIR="$ROOT" PATH="$ROOT/fakebin:$PATH" MOCK_PKGS="samba"

printf '[global]\n   workgroup = WORKGROUP\n\n[printers]\n   path = /tmp\n' > "$ROOT/smb.conf"

PASS=0; FAIL=0
check() { if eval "$2"; then printf '  PASS %s\n' "$1"; PASS=$((PASS+1))
          else printf '  FAIL %s   [%s]\n' "$1" "$2"; FAIL=$((FAIL+1)); fi; }
run_mod() { # modul extra-env…
    local mod=$1; shift
    env MUSIK_INSTALLER_STATE="$ROOT/state" INSTALLER_PROJECT_DIR="$ROOT" \
        INSTALLER_SMBCONF="$ROOT/smb.conf" INSTALLER_NONINTERACTIVE=1 \
        "$@" bash "$ROOT/mods/$mod" 2>&1
}

echo "== Szenario 1: Freigabe anlegen (kein OMV, Library vorhanden) =="
rm -rf "$ROOT/state"; mkdir -p "$ROOT/state"
echo "MOD_detect=ok" > "$ROOT/state/state.env"
echo "ANSWER_library=$ROOT/lib-music" >> "$ROOT/state/state.env"
out=$(run_mod 32-samba.sh) || true
check "Modul ok"                         "echo \"\$out\" | grep -q 'SMB-Freigabe'"
check "Share-Block mit force user"       "grep -q '^ *force user = ' '$ROOT/smb.conf'"
check "Pfad zeigt auf Library"           "grep -q \"path = \$ROOT/lib-music\" '$ROOT/smb.conf'"
check "map-to-guest im [global]"         "grep -A1 '^\\[global\\]' '$ROOT/smb.conf' | grep -q 'map to guest = Bad User'"
check "nur EIN [global]-Block"           "[[ \$(grep -c '^\\[global\\]' '$ROOT/smb.conf') -eq 1 ]]"

echo "== Szenario 2: Idempotenz — zweiter Lauf ändert nichts =="
cp "$ROOT/smb.conf" "$ROOT/smb.before"
out=$(run_mod 32-samba.sh) || true
check "Marker unverändert doppelt vermeiden" "[[ \$(grep -c 'musik-installer share' '$ROOT/smb.conf') -eq 1 ]]"
check "Konfig byte-identisch"            "cmp -s '$ROOT/smb.before' '$ROOT/smb.conf'"

echo "== Szenario 3: OMV installiert → Modul tritt zurück =="
rm -rf "$ROOT/state"; mkdir -p "$ROOT/state"
{ echo "MOD_detect=ok"; echo "ANSWER_library=$ROOT/lib-music"; } > "$ROOT/state/state.env"
out=$(MOCK_PKGS="samba openmediavault" run_mod 32-samba.sh) || true
check "Skip-Meldung"                     "echo \"\$out\" | grep -q 'OMV verwaltet SMB'"

echo "== Szenario 4: omv-Modul auf Ubuntu → ehrlicher Skip =="
rm -rf "$ROOT/state"; mkdir -p "$ROOT/state"
{ echo "MOD_detect=ok"; echo "ANSWER_omv_supported=0"; echo "ANSWER_os_id=ubuntu"; } > "$ROOT/state/state.env"
out=$(run_mod 30-omv.sh) || true
check "Skip mit Begründung"              "echo \"\$out\" | grep -q 'nicht vorgesehen'"

echo
echo "================ ERGEBNIS: $PASS bestanden, $FAIL fehlgeschlagen ==============="
[[ $FAIL -eq 0 ]]
