#!/usr/bin/env bash
# harness_verify.sh — Logik-Tests für install.d/90-verify.sh (Story 8.6):
# Report-Karte auf einem „voll ausgestatteten“ und einem „leeren“ System.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT=$(mktemp -d "${TMPDIR:-/tmp}/musik-verify-harness.XXXXXX")
trap 'echo "Harness-Verzeichnis: $ROOT"' EXIT
mkdir -p "$ROOT/fakebin" "$ROOT/mods/lib" "$ROOT/state" "$ROOT/proj/.venv/bin" "$ROOT/lib-music"
cp "$REPO/install.d/lib/common.sh" "$ROOT/mods/lib/"
cp "$REPO/install.d/90-verify.sh" "$ROOT/mods/"
touch "$ROOT/proj/.venv/bin/python" && chmod +x "$ROOT/proj/.venv/bin/python" 2>/dev/null || true
printf '{"token": "x"}\n' > "$ROOT/proj/telegram_token.json"
printf '# youtube cookies\n' > "$ROOT/proj/cookies.txt"

cat > "$ROOT/fakebin/findmnt" <<EOF
#!/usr/bin/env bash
[[ "\$1" == "\$MOCK_MUSIC" ]] && { echo "TARGET SOURCE FSTYPE"; echo "\$MOCK_MUSIC /dev/sdb btrfs rw"; exit 0; }
exit 1
EOF
cat > "$ROOT/fakebin/systemctl" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "is-enabled" || "$1" == "is-active" ]] && { echo "$1"; exit 0; }
exit 0
EOF
cat > "$ROOT/fakebin/dpkg-query" <<'EOF'
#!/usr/bin/env bash
pkg="${@: -1}"
case " ${MOCK_PKGS:-} " in *" $pkg "*) echo "install ok installed"; exit 0 ;; esac
exit 1
EOF
cat > "$ROOT/fakebin/docker" <<'EOF'
#!/usr/bin/env bash
[[ "$1 $2" == "inspect -f" ]] && { echo true; exit 0; }
[[ "$1" == "--version" ]] && { echo "Docker version 26.1.4"; exit 0; }
[[ "$1" == "info" ]] && exit 0
exit 0
EOF
printf '#!/usr/bin/env bash\nexit 0\n' > "$ROOT/fakebin/curl"
printf '#!/usr/bin/env bash\nif [[ -f /usr/bin/smbd ]]; then exit 0; fi\nexit 1\n' > "$ROOT/fakebin/smbd" 2>/dev/null || true
cat > "$ROOT/fakebin/sudo" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "-u" ]] && shift 2
"$@"
EOF
chmod +x "$ROOT"/fakebin/*
export MOCKDIR="$ROOT" PATH="$ROOT/fakebin:$PATH" MOCK_MUSIC="$ROOT/lib-music"

PASS=0; FAIL=0
check() { if eval "$2"; then printf '  PASS %s\n' "$1"; PASS=$((PASS+1))
          else printf '  FAIL %s   [%s]\n' "$1" "$2"; FAIL=$((FAIL+1)); fi; }
run_verify() { env MUSIK_INSTALLER_STATE="$ROOT/state" INSTALLER_PROJECT_DIR="$ROOT/proj" \
    INSTALLER_NONINTERACTIVE=1 INSTALLER_MUSIC_MOUNT="$ROOT/lib-music" \
    "$@" bash "$ROOT/mods/90-verify.sh" 2>&1; }

echo "== Szenario 1: voll ausgestatteter Host (alles ✓, keine offenen Pflichten) =="
rm -rf "$ROOT/state"; mkdir -p "$ROOT/state"; echo "MOD_detect=ok" > "$ROOT/state/state.env"
echo "ANSWER_library=$ROOT/lib-music" >> "$ROOT/state/state.env"
cat > "$ROOT/proj/config.yaml" <<'EOF'
musik:
    bot_allowlist: [123456789]
    plex:
        url: http://127.0.0.1:32400
        token: TOK
        section: Musik
EOF
mkdir -p "$ROOT/plexdir"; printf '<Preferences PlexOnlineToken="T" />\n' > "$ROOT/plexdir/Preferences.xml"
out=$(MOCK_PKGS="plexmediaserver openmediavault" run_verify INSTALLER_PLEX_PREFS="$ROOT/plexdir/Preferences.xml") || true
check "Musik-Root ✓"              "echo \"\$out\" | grep -q 'Musik-Root.*gemountet'"
check "musik-Tool ✓"              "echo \"\$out\" | grep -q 'musik-Tool (venv'"
check "beide Units ✓"             "echo \"\$out\" | grep -q 'musik-ingest.timer (enabled + aktiv)'"
check "Docker ✓"                  "echo \"\$out\" | grep -q 'Docker (Docker version'"
check "MG ✓"                      "echo \"\$out\" | grep -q 'MusicGrabber (Container läuft'"
check "Plex ✓"                    "echo \"\$out\" | grep -q 'Plex Media Server (API'"
check "OMV-Freigabe ✓"            "echo \"\$out\" | grep -q 'OpenMediaVault verwaltet'"
check "keine manuellen Pflichten" "echo \"\$out\" | grep -q 'Keine manuellen Schritte offen'"
check "Modul failt nie (ok)"      "echo \"\$out\" | grep -q 'Report-Karte erstellt'"

echo "== Szenario 2: leerer Host (alles —, Hinweise statt Absturz) =="
rm -rf "$ROOT/state" "$ROOT/lib-music"; mkdir -p "$ROOT/state"
echo "MOD_detect=ok" > "$ROOT/state/state.env"
rm -f "$ROOT/proj/config.yaml" "$ROOT/proj/telegram_token.json" "$ROOT/proj/cookies.txt"
out=$(run_verify) || true
check "kein Musik-Root markiert"  "echo \"\$out\" | grep -q 'kein Musik-Root'"
check "Tool unvollständig"        "echo \"\$out\" | grep -q 'musik-Tool unvollständig'"
check "Plex nicht installiert"    "echo \"\$out\" | grep -q 'Plex nicht installiert'"
check "Modul trotzdem ok"         "echo \"\$out\" | grep -q 'Report-Karte erstellt'"

echo
echo "================ ERGEBNIS: $PASS bestanden, $FAIL fehlgeschlagen ==============="
[[ $FAIL -eq 0 ]]
