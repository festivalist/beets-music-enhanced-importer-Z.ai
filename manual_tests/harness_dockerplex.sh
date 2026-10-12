#!/usr/bin/env bash
# harness_dockerplex.sh — Logik-Tests für 40-docker.sh und 50-plex.sh
# (Story 8.4): Docker-Installation inkl. arch-bewusstem Compose-Binary und
# docker-cli-Falle, Plex-Assistenz mit Token/Claim-Pfaden und dem
# config.yaml-plex-Block-Setter (echtes Python über das Repo-venv).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT=$(mktemp -d "${TMPDIR:-/tmp}/musik-dpx-harness.XXXXXX")
trap 'echo "Harness-Verzeichnis: $ROOT"' EXIT
mkdir -p "$ROOT/fakebin" "$ROOT/mods/lib" "$ROOT/state" "$ROOT/compose-dir" "$ROOT/proj"
cp "$REPO/install.d/lib/common.sh" "$ROOT/mods/lib/"
cp "$REPO/install.d/40-docker.sh" "$REPO/install.d/50-plex.sh" "$ROOT/mods/"

VENV_PY="$REPO/.venv/Scripts/python.exe"
[[ -x "$VENV_PY" ]] || VENV_PY="$REPO/.venv/bin/python"
[[ -x "$VENV_PY" ]] || { echo "Brauche das Repo-.venv-Python für den Plex-Setter-Test"; exit 1; }

cat > "$ROOT/fakebin/python3" <<EOF
#!/usr/bin/env bash
exec "$VENV_PY" "\$@"
EOF
cat > "$ROOT/fakebin/dpkg-query" <<'EOF'
#!/usr/bin/env bash
pkg="${@: -1}"
case " ${MOCK_PKGS:-} " in *" $pkg "*) echo "install ok installed"; exit 0 ;; esac
exit 1
EOF
cat > "$ROOT/fakebin/docker" <<'EOF'
#!/usr/bin/env bash
if [[ "$1 $2" == "compose version" ]]; then
  # MSYS-/tmp honoriert chmod +x nicht (noacl-Mount) → -f statt -x
  if [[ -f "$MOCK_COMPOSE_BIN" ]]; then echo "Docker Compose version v2.29.7"; exit 0; fi
  exit 1
fi
if [[ "$1" == "--version" ]]; then echo "Docker version 26.1.4, build 5470ff1"; exit 0; fi
exit 0
EOF
cat > "$ROOT/fakebin/curl" <<'EOF'
#!/usr/bin/env bash
# -fsSL <url> -o <file> → Datei anlegen (Compose-/Deb-Download simuliert)
for a in "$@"; do last="$a"; done
out=""
prev=""
for a in "$@"; do [[ "$prev" == "-o" ]] && out="$a"; prev="$a"; done
[[ -n "$out" ]] && { echo "mock-binary" > "$out"; exit 0; }
[[ "$last" == *.json ]] && { echo '{"releases":[]}'; exit 0; }
exit 0
EOF
for m in apt-get systemctl gpg usermod tee mv; do
  printf '#!/usr/bin/env bash\n[[ "$1" == "is-active" ]] && { echo active; exit 0; }\nexit 0\n' > "$ROOT/fakebin/$m"
done
cat > "$ROOT/fakebin/sudo" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "-u" ]] && shift 2
"$@"
EOF
chmod +x "$ROOT"/fakebin/*
export MOCKDIR="$ROOT" PATH="$ROOT/fakebin:$PATH" MOCK_COMPOSE_BIN="$ROOT/compose-dir/docker-compose"

PASS=0; FAIL=0
check() { if eval "$2"; then printf '  PASS %s\n' "$1"; PASS=$((PASS+1))
          else printf '  FAIL %s   [%s]\n' "$1" "$2"; FAIL=$((FAIL+1)); fi; }
reset_state() { rm -rf "$ROOT/state"; mkdir -p "$ROOT/state"
    { echo "MOD_detect=ok"; echo "ANSWER_arch=amd64"; echo "ANSWER_os_id=debian"; } > "$ROOT/state/state.env"
    rm -f "$ROOT/compose-dir/docker-compose" "$ROOT/mock.log"; }
run_mod() { local mod=$1; shift
    env MUSIK_INSTALLER_STATE="$ROOT/state" INSTALLER_PROJECT_DIR="$ROOT/proj" \
        INSTALLER_NONINTERACTIVE=1 INSTALLER_COMPOSE_DIR="$ROOT/compose-dir" \
        "$@" bash "$ROOT/mods/$mod" 2>&1; }

echo "== Szenario 1: Docker-Installation (amd64, docker-cli-Falle abgedeckt) =="
reset_state
out=$(run_mod 40-docker.sh) || true
check "Modul ok"                          "echo \"\$out\" | grep -q 'Docker + Compose v2 bereit'"
check "docker erkannt/installiert"        "echo \"\$out\" | grep -q -e 'docker.io installiert' -e 'docker bereits'"
check "Compose-Binary geladen"            "[[ -f '$ROOT/compose-dir/docker-compose' ]]"
check "usermod docker-Gruppe"             "echo \"\$out\" | grep -q 'docker-Gruppe'"

echo "== Szenario 2: Docker schon da + Compose ok → idempotent =="
out=$(run_mod 40-docker.sh) || true
check "zweiter Lauf ohne Neuinstallation" "echo \"\$out\" | grep -q 'bereits nutzbar'"

echo "== Szenario 3: Plex installiert, NICHT geclaimt → ok + UI-Hinweis =="
reset_state; export MOCK_PKGS="plexmediaserver"
out=$(run_mod 50-plex.sh) || true
check "Claim-Hinweis"                     "echo \"\$out\" | grep -q 'noch nicht geclaimt'"
check "Berechtigungs-Hinweis"             "echo \"\$out\" | grep -q 'Leserechte'"

echo "== Szenario 4: Plex geclaimt → config.yaml-plex-Block (kommentierte Platzhalter) =="
reset_state
mkdir -p "$ROOT/proj"
printf 'directory: /tmp/x\n\nmusik:\n    plex:\n        # url: http://plexpi:32400\n        # token: YOUR-X-PLEX-TOKEN\n        # section: Musik\n    fetch:\n        cookies_file: cookies.txt\n' > "$ROOT/proj/config.yaml"
mkdir -p "$ROOT/plexdir"
printf '<Preferences PlexOnlineToken="TOKEN-XY-123" />\n' > "$ROOT/plexdir/Preferences.xml"
out=$(run_mod 50-plex.sh INSTALLER_PLEX_PREFS="$ROOT/plexdir/Preferences.xml") || true
cfg="$ROOT/proj/config.yaml"
check "url gesetzt"                       "grep -q 'url: http://127.0.0.1:32400' '$cfg'"
check "token gesetzt"                     "grep -q 'token: TOKEN-XY-123' '$cfg'"
check "section gesetzt"                   "grep -q '^        section: Musik' '$cfg'"
check "alte Platzhalter weg"              "! grep -q 'YOUR-X-PLEX-TOKEN' '$cfg'"
check "nachfolgender fetch-Block intakt"  "grep -A2 'plex:' '$cfg' | head -1 >/dev/null && grep -q 'cookies_file' '$cfg'"
check "Backup der config erstellt"        "ls '$ROOT/proj'/config.yaml.bak.* >/dev/null 2>&1"
check "genau EIN plex:-Block"             "[[ \$(grep -c 'plex:' '$cfg') -eq 1 ]]"

echo "== Szenario 5: config OHNE plex-Block → wird unter musik: eingefügt =="
reset_state
printf 'directory: /tmp/x\n\nmusik:\n    fetch:\n        cookies_file: cookies.txt\n' > "$ROOT/proj/config.yaml"
out=$(run_mod 50-plex.sh INSTALLER_PLEX_PREFS="$ROOT/plexdir/Preferences.xml") || true
check "plex-Block eingefügt"              "grep -q '^    plex:' '$ROOT/proj/config.yaml'"
check "token drin"                        "grep -q 'token: TOKEN-XY-123' '$ROOT/proj/config.yaml'"
check "fetch weiterhin da"                "grep -q 'cookies_file' '$ROOT/proj/config.yaml'"

echo
echo "================ ERGEBNIS: $PASS bestanden, $FAIL fehlgeschlagen ==============="
[[ $FAIL -eq 0 ]]
