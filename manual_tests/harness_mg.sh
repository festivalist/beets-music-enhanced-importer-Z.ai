#!/usr/bin/env bash
# harness_mg.sh — Logik-Tests für install.d/70-musicgrabber.sh (Story 8.5):
# Staging-Anker host-seitig, .env aus Example mit PUID/PGID des Run-Users,
# Idempotenz (.env bleibt unangetastet), Container-Probe-Pfad.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT=$(mktemp -d "${TMPDIR:-/tmp}/musik-mg-harness.XXXXXX")
trap 'echo "Harness-Verzeichnis: $ROOT"' EXIT
mkdir -p "$ROOT/fakebin" "$ROOT/mods/lib" "$ROOT/state" "$ROOT/proj/musicgrabber" "$ROOT/lib-music"
cp "$REPO/install.d/lib/common.sh" "$ROOT/mods/lib/"
cp "$REPO/install.d/70-musicgrabber.sh" "$ROOT/mods/"
cp "$REPO/musicgrabber/.env.example" "$ROOT/proj/musicgrabber/.env.example"
mkdir -p "$ROOT/proj/musicgrabber/overlay/static"
printf '<html>overlay</html>' > "$ROOT/proj/musicgrabber/overlay/static/index.html"

cat > "$ROOT/fakebin/docker" <<'EOF'
#!/usr/bin/env bash
case "$1 $2" in
  "compose ps")   printf 'NAME IMAGE COMMAND SERVICE\nmusicgrabber g33kphr33k/musicgrabber:4.3.1 Up musicgrabber\n'; exit 0 ;;
  "inspect -f")   echo true; exit 0 ;;   # Container läuft (Up-Pfad übersprungen)
esac
exit 0
EOF
cat > "$ROOT/fakebin/curl" <<'EOF'
#!/usr/bin/env bash
exit 0    # Web-UI-Probe sofort erfolgreich
EOF
cat > "$ROOT/fakebin/sudo" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "-u" ]] && shift 2
"$@"
EOF
chmod +x "$ROOT"/fakebin/*
export MOCKDIR="$ROOT" PATH="$ROOT/fakebin:$PATH"

PASS=0; FAIL=0
check() { if eval "$2"; then printf '  PASS %s\n' "$1"; PASS=$((PASS+1))
          else printf '  FAIL %s   [%s]\n' "$1" "$2"; FAIL=$((FAIL+1)); fi; }
run_mod() { env MUSIK_INSTALLER_STATE="$ROOT/state" INSTALLER_PROJECT_DIR="$ROOT/proj" \
    INSTALLER_NONINTERACTIVE=1 INSTALLER_MG_WAIT=0 INSTALLER_MUSIC_MOUNT="$ROOT/lib-music" \
    "$@" bash "$ROOT/mods/70-musicgrabber.sh" 2>&1; }
reset_state() { rm -rf "$ROOT/state" "$ROOT/lib-music"; mkdir -p "$ROOT/state" "$ROOT/lib-music"
    echo "MOD_detect=ok" > "$ROOT/state/state.env"; rm -f "$ROOT/proj/musicgrabber/.env"; }

echo "== Szenario 1: Frisch-Deploy (Anker, .env, Probe) =="
reset_state
out=$(run_mod) || true
check "Modul ok"                      "echo \"\$out\" | grep -q 'MusicGrabber läuft'"
check "Anker Singles angelegt"        "[[ -d '$ROOT/lib-music/_incoming/musicgrabber/Singles' ]]"
check "Anker Albums angelegt"         "[[ -d '$ROOT/lib-music/_incoming/musicgrabber/Albums' ]]"
check "Anker Playlists angelegt"      "[[ -d '$ROOT/lib-music/_incoming/musicgrabber/Playlists' ]]"
uid=$(id -u)
check ".env mit PUID des Users"       "grep -q \"^PUID=$uid\" '$ROOT/proj/musicgrabber/.env'"
check "kein API_KEY gesetzt"          "! grep -q '^MUSICGRABBER_API_KEY' '$ROOT/proj/musicgrabber/.env'"

echo "== Szenario 2: Idempotenz — .env bleibt unangetastet =="
cp "$ROOT/proj/musicgrabber/.env" "$ROOT/env.before"
out=$(run_mod) || true
check ".env unverändert"              "cmp -s '$ROOT/env.before' '$ROOT/proj/musicgrabber/.env'"
check "Container-läuft-Pfad"          "echo \"\$out\" | grep -q 'Container läuft bereits'"

echo "== Szenario 3: ohne Musik-Root → sauberer Skip =="
rm -rf "$ROOT/state" "$ROOT/lib-music"; mkdir -p "$ROOT/state"
echo "MOD_detect=ok" > "$ROOT/state/state.env"
out=$(run_mod) || true
check "Skip mit Hinweis"              "echo \"\$out\" | grep -q 'kein Musik-Root'"

echo "== Szenario 4: Overlay fehlt → klarer Fail (ADR-0001) =="
reset_state
rm -f "$ROOT/proj/musicgrabber/overlay/static/index.html"
out=$(run_mod) || true
check "Overlay-Fail mit Hinweis"      "echo \"\$out\" | grep -q 'overlay/static/index.html fehlt'"
check "kein .env angelegt bei Fail"   "[[ ! -f '$ROOT/proj/musicgrabber/.env' ]]"
printf '<html>overlay</html>' > "$ROOT/proj/musicgrabber/overlay/static/index.html"

echo
echo "================ ERGEBNIS: $PASS bestanden, $FAIL fehlgeschlagen ==============="
[[ $FAIL -eq 0 ]]
