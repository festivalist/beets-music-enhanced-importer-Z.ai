#!/usr/bin/env bash
# musik one-shot installer — modularer Treiber (EPIC 8, Stories 8.1+).
#
# Parität zu install.ps1 bleibt bestehen: Python >= 3.10, venv, pip-Deps,
# native Tools, Setup-Wizard, systemd-Service für den Telegram-Bot.
# Darüber hinaus (EPIC 8): OS-Erkennung, Festplatten, OMV (optional,
# Debian-only), Docker, Plex, MusicGrabber — alles als Module in install.d/,
# mit Resume-State und Generalprobe.
#
# Usage:
#   bash install.sh                      interaktive Komplett-Installation
#                                        (setzt automatisch fort, falls ein
#                                        früherer Lauf abbrach)
#   bash install.sh --core-only          nur Systempakete + musik-Tool
#                                        (altes Verhalten vor EPIC 8)
#   bash install.sh --library /mnt/x     Musikwurzel durchreichen (Wizard)
#   bash install.sh --no-systemd         systemd-Units weglassen
#   bash install.sh --resume             unvollständigen Lauf fortsetzen
#                                        (auch der Default)
#   bash install.sh --fresh              State verwerfen, neu beginnen
#   bash install.sh --add-disk           Festplatte nachträglich einbinden
#   bash install.sh --only <module,…>    nur bestimmte Module (Namen: --list)
#   bash install.sh --dry-run            Generalprobe: zeigt Aktionen
#                                        (inkl. destruktive), ändert nichts
#   bash install.sh --answers <file>     Antworten vorab (env-Stil:
#                                        ANSWER_disks_fs=btrfs …)
#   bash install.sh --non-interactive    nie fragen; fehlende Antworten
#                                        überspringen/failen das Modul
#   bash install.sh --list               verfügbare Module anzeigen
#
# Modul-Konvention (siehe install.d/lib/common.sh): Module laufen als eigene
# Prozesse — Exit 0 = ok, 77 = übersprungen, 78/sonst = fehlgeschlagen. Der
# Treiber stirbt nie am Modul-Crash: Pflichtmodule beenden den Lauf mit
# Resume-Hinweis, Optionalmodule werden übersprungen, der Rest läuft weiter.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export INSTALLER_PROJECT_DIR="$PROJECT_DIR"
MODULE_DIR="${MUSIK_INSTALLER_MODULES:-$PROJECT_DIR/install.d}"

if [[ ! -f "$MODULE_DIR/lib/common.sh" ]]; then
    echo "FEHLER: $MODULE_DIR/lib/common.sh fehlt — Repo unvollständig?" >&2
    exit 1
fi
# shellcheck source=install.d/lib/common.sh
source "$MODULE_DIR/lib/common.sh"

CORE_ONLY=0; FRESH=0; ADD_DISK=0; ONLY=""; ANSWERS_FILE=""; LIST=0
LIBRARY_ARG=""; NO_SYSTEMD=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --core-only)       CORE_ONLY=1; shift ;;
        --resume)          shift ;;   # Default-Verhalten; Flag für Skripte/CI
        --fresh)           FRESH=1; shift ;;
        --add-disk)        ADD_DISK=1; shift ;;
        --only)            ONLY="${2:?--only braucht Modulnamen}"; shift 2 ;;
        --dry-run)         export INSTALLER_DRY_RUN=1; shift ;;
        --answers)         ANSWERS_FILE="${2:?--answers braucht eine Datei}"; shift 2 ;;
        --non-interactive) export INSTALLER_NONINTERACTIVE=1; shift ;;
        --library)         LIBRARY_ARG="${2:?--library braucht einen Pfad}"; shift 2 ;;
        --no-systemd)      NO_SYSTEMD=1; shift ;;
        --list)            LIST=1; shift ;;
        -h|--help)         grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unbekannte Option: $1 (siehe --help)" >&2; exit 1 ;;
    esac
done
export INSTALLER_NO_SYSTEMD=$NO_SYSTEMD
export INSTALLER_ADD_DISK=$ADD_DISK
export INSTALLER_CORE_ONLY=$CORE_ONLY

# --- State-Verzeichnis ---------------------------------------------------------
ensure_state_dir() {
    if [[ -n "${MUSIK_INSTALLER_STATE:-}" ]]; then
        mkdir -p "$MUSIK_INSTALLER_STATE" 2>/dev/null || true
        INSTALLER_STATE_DIR="$MUSIK_INSTALLER_STATE"
    else
        local dir="/var/lib/musik-installer"
        if [[ -d "$dir" && -w "$dir" ]]; then
            INSTALLER_STATE_DIR="$dir"
        elif mkdir -p "$dir" 2>/dev/null && [[ -w "$dir" ]]; then
            INSTALLER_STATE_DIR="$dir"
        elif [[ $EUID -eq 0 ]] && mkdir -p "$dir" 2>/dev/null; then
            INSTALLER_STATE_DIR="$dir"
        elif command -v sudo >/dev/null 2>&1 \
             && sudo mkdir -p "$dir" 2>/dev/null \
             && sudo chown "$(id -u):$(id -g)" "$dir" 2>/dev/null \
             && [[ -w "$dir" ]]; then
            INSTALLER_STATE_DIR="$dir"
        else
            INSTALLER_STATE_DIR="$PROJECT_DIR/state/installer"
            mkdir -p "$INSTALLER_STATE_DIR"
            warn "State-Fallback $INSTALLER_STATE_DIR (gitignored) — /var/lib/musik-installer nicht anlegbar."
        fi
    fi
    export INSTALLER_STATE_DIR
    INSTALLER_STATE_FILE="$INSTALLER_STATE_DIR/state.env"
    export INSTALLER_STATE_FILE
    INSTALLER_LOG_FILE="$INSTALLER_STATE_DIR/installer.log"
    export INSTALLER_LOG_FILE
    log "=== installer gestartet (Modus: $([[ $CORE_ONLY == 1 ]] && echo core-only || echo voll)$([[ ${INSTALLER_DRY_RUN:-0} == 1 ]] && echo ', dry-run')) ==="
}

# --- Module entdecken + Metadaten -------------------------------------------------
# Metadaten-Zeile in jedem Modul:  #MODULE name|Anzeigetext|deps|required(0/1)
discover_modules() {
    MODULES_FILE=(); MODULES_NAME=(); MODULES_DISP=(); MODULES_DEPS=(); MODULES_REQ=()
    local f meta name disp deps req
    for f in "$MODULE_DIR"/[0-9]*.sh; do
        [[ -e "$f" ]] || continue
        meta=$(sed -n 's/^#MODULE //p' "$f" | head -1)
        [[ -n "$meta" ]] || { warn "$(basename "$f") hat keine #MODULE-Zeile — ignoriert."; continue; }
        IFS='|' read -r name disp deps req <<< "$meta"
        MODULES_FILE+=("$f"); MODULES_NAME+=("$name")
        MODULES_DISP+=("$disp"); MODULES_DEPS+=("${deps:-}"); MODULES_REQ+=("${req:-0}")
    done
}

list_modules() {
    printf 'Verfügbare Module (%s):\n\n' "$MODULE_DIR"
    printf '  %-14s %-6s %-14s %s\n' "NAME" "PFICHT" "BRAUCHT" "BESCHREIBUNG"
    local i
    for i in "${!MODULES_NAME[@]}"; do
        printf '  %-14s %-6s %-14s %s\n' \
            "${MODULES_NAME[$i]}" "$([[ ${MODULES_REQ[$i]} == 1 ]] && echo ja || echo nein)" \
            "${MODULES_DEPS[$i]:-—}" "${MODULES_DISP[$i]}"
    done
    printf '\nAufruf: bash install.sh --only disks,plex   (oder komplett ohne Flag)\n'
}

plan_modules() { # setzt PLAN_*-Arrays
    PLAN_IDX=()
    local i name found
    if [[ $ADD_DISK == 1 ]]; then
        for i in "${!MODULES_NAME[@]}"; do
            [[ "${MODULES_NAME[$i]}" == "disks" ]] && PLAN_IDX+=("$i")
        done
        if [[ ${#PLAN_IDX[@]} -eq 0 ]]; then
            err "Kein Platten-Modul gefunden — --add-disk braucht install.d/20-disks.sh."
            exit 1
        fi
        return 0
    fi
    if [[ -n "$ONLY" ]]; then
        IFS=',' read -ra WANTED <<< "$ONLY"
        for name in "${WANTED[@]}"; do
            name=$(echo "$name" | xargs)   # Whitespace trimmen
            found=""
            for i in "${!MODULES_NAME[@]}"; do
                [[ "${MODULES_NAME[$i]}" == "$name" ]] && { PLAN_IDX+=("$i"); found=1; break; }
            done
            [[ -n "$found" ]] || { err "Unbekanntes Modul '$name' — verfügbare: --list"; exit 1; }
        done
        return 0
    fi
    for i in "${!MODULES_NAME[@]}"; do
        if [[ $CORE_ONLY == 1 ]]; then
            case "${MODULES_NAME[$i]}" in detect|base|musik) ;; *) continue ;; esac
        fi
        PLAN_IDX+=("$i")
    done
}

# --- Los -------------------------------------------------------------------------
discover_modules
if [[ $LIST == 1 ]]; then list_modules; exit 0; fi

if [[ $EUID -ne 0 ]] && ! have sudo && [[ ${MUSIK_INSTALLER_TEST:-0} != 1 ]]; then
    # MUSIK_INSTALLER_TEST=1 ist der dokumentierte Escape für die Treiber-
    # Logiktests (Dummy-Module, kein Systemkontakt); Produktion bleibt hart.
    err "Weder root noch sudo verfügbar — Systemmodule können nicht installiert werden."
    exit 1
fi

ensure_state_dir
if [[ $FRESH == 1 ]]; then
    rm -f "$INSTALLER_STATE_FILE"
    ok "State verworfen (--fresh) — Antworten müssen neu gegeben werden."
fi
# State ggf. erneut laden (Verzeichnis kann gerade erst gewählt worden sein)
if [[ -r "$INSTALLER_STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$INSTALLER_STATE_FILE" || true
fi
if [[ -n "$ANSWERS_FILE" ]]; then
    [[ -r "$ANSWERS_FILE" ]] || { err "Answers-Datei nicht lesbar: $ANSWERS_FILE"; exit 1; }
    # Zeilenweises Parsen statt source: Werte mit Leerzeichen brauchen kein
    # Quoting, und eine kaputte Zeile bringt den Installer nicht zum Absturz.
    # Format: ANSWER_<key>=Wert   (optional in '…' oder "…" eingefasst)
    n_answers=0
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" || "$line" == \#* ]] && continue
        [[ "$line" == ANSWER_*=* ]] || { warn "Answers-Datei: Zeile ignoriert (erwartet ANSWER_key=wert): $line"; continue; }
        akey=${line%%=*}; aval=${line#*=}
        if [[ "$aval" == \"*\" && "$aval" == *\" ]]; then aval=${aval:1:-1}
        elif [[ "$aval" == \'*\' && "$aval" == *\' ]]; then aval=${aval:1:-1}; fi
        state_set "$akey" "$aval"
        n_answers=$((n_answers+1))
    done < "$ANSWERS_FILE"
    ok "$n_answers Antwort(en) aus $(basename "$ANSWERS_FILE") übernommen."
fi
[[ -n "$LIBRARY_ARG" ]] && state_set ANSWER_library "$LIBRARY_ARG"

plan_modules

printf '\n=== musik one-shot installer ===\n'
printf 'Host: %s | User: %s | Module: %s | State: %s\n' \
    "$(uname -sr)" "$(id -un)" "${#PLAN_IDX[@]}" "$INSTALLER_STATE_FILE"
[[ ${INSTALLER_DRY_RUN:-0} == 1 ]] && printf '>>> DRY-RUN: nichts wird geändert, Modulstatus wird nicht gespeichert.\n'
[[ $CORE_ONLY == 1 ]] && printf '>>> Core-Only: nur Systempakete + musik-Tool (altes Verhalten).\n'
[[ $ADD_DISK == 1 ]] && printf '>>> Add-Disk-Modus: nur Platten-Modul (Festplatte nachträglich einbinden).\n'

trap 'err "Abbruch — Fortschritt bleibt im State; nächster Lauf setzt automatisch fort (bzw. --resume)."' INT TERM

FAILED=0; SKIPPED=0; DONE_NOW=0; RESUMED_OK=0
# Laufzeit-Status dieses Laufs (auch im Dry-Run befüllt, aber nie persistiert):
# Abhängigkeitsprüfungen und Zusammenfassung sehen sonst im Dry-Run nichts,
# weil finish() dort bewusst keinen MOD_*-Status schreibt.
declare -A RUNTIME_MOD=()
mod_status() { # name → Laufzeit-Status vor State-Status
    if [[ -n "${RUNTIME_MOD[$1]:-}" ]]; then printf '%s' "${RUNTIME_MOD[$1]}";
    else state_get "MOD_$1" ""; fi
}

for i in "${PLAN_IDX[@]}"; do
    name="${MODULES_NAME[$i]}"; disp="${MODULES_DISP[$i]}"
    deps="${MODULES_DEPS[$i]}"; req="${MODULES_REQ[$i]}"

    st=$(mod_status "$name")
    if [[ "$st" == "ok" && ${INSTALLER_DRY_RUN:-0} != 1 ]]; then
        printf '\n✓ %-14s bereits erledigt — übersprungen (Resume)\n' "$name"
        RESUMED_OK=$((RESUMED_OK+1))
        continue
    fi

    # Abhängigkeiten: müssen 'ok' sein, sonst abhängiges Modul nicht starten
    unmet=""
    for d in $deps; do
        dst=$(mod_status "$d")
        [[ "$dst" == "ok" ]] || unmet+="${d}=${dst:-fehlt} "
    done
    if [[ -n "$unmet" ]]; then
        RUNTIME_MOD[$name]=skip
        if [[ "$req" == "1" ]]; then
            err "Pflichtmodul '$name' kann nicht laufen — Abhängigkeiten nicht ok: $unmet"
            err "Erst die Abhängigkeiten beheben (--resume), dann weiter."
            exit 1
        fi
        printf '\n- %-14s übersprungen (Abhängigkeiten: %s)\n' "$name" "$unmet"
        [[ ${INSTALLER_DRY_RUN:-0} == 1 ]] || mod_set "$name" skip "Abhängigkeiten nicht ok: $unmet"
        SKIPPED=$((SKIPPED+1))
        continue
    fi

    step "Modul: $disp ($name)"
    rc=0
    bash "${MODULES_FILE[$i]}" || rc=$?
    case "$rc" in
        0)  RUNTIME_MOD[$name]=ok; DONE_NOW=$((DONE_NOW+1)); log "TREIBER: $name rc=0" ;;
        77) RUNTIME_MOD[$name]=skip; printf '    → übersprungen.\n'; SKIPPED=$((SKIPPED+1)); log "TREIBER: $name rc=77 (skip)" ;;
        78) RUNTIME_MOD[$name]=fail; FAILED=$((FAILED+1)); log "TREIBER: $name rc=78 (fail)"
            if [[ "$req" == "1" ]]; then
                err "Pflichtmodul '$name' fehlgeschlagen — Lauf stoppt hier."
                err "Beheben und fortfahren:  bash install.sh --resume"
                exit 1
            fi
            if [[ ${INSTALLER_NONINTERACTIVE:-0} != 1 ]]; then
                answer="j"
                read -r -p "    Optionalmodul fehlgeschlagen — trotzdem fortfahren? ([j]a/[n]ein): " answer || answer="j"
                [[ "$answer" == n* ]] && { err "Abgebrochen — --resume setzt später fort."; exit 1; }
            fi
            ;;
        *)  RUNTIME_MOD[$name]=fail; FAILED=$((FAILED+1)); log "TREIBER: $name rc=$rc (unerwartet)"
            if [[ "$req" == "1" ]]; then
                err "Pflichtmodul '$name' ist unerwartet abgestürzt (rc=$rc) — Lauf stoppt."
                err "Log: $INSTALLER_LOG_FILE — danach:  bash install.sh --resume"
                exit 1
            fi
            warn "Optionalmodul '$name' abgestürzt (rc=$rc) — wird als fehlgeschlagen weitergeführt." ;;
    esac
done

# --- Zusammenfassung ---------------------------------------------------------------
printf '\n=== Zusammenfassung ===\n'
for i in "${PLAN_IDX[@]}"; do
    name="${MODULES_NAME[$i]}"
    st=$(mod_status "$name")
    note=$(state_get "MOD_${name}_note" "")
    icon="?"; case "$st" in ok) icon="✓" ;; skip) icon="-" ;; fail) icon="✗" ;; esac
    printf '  %s %-14s %s%s\n' "$icon" "$name" "${st:-nicht gelaufen}" "${note:+ — $note}"
done
printf '\n'
[[ $RESUMED_OK -gt 0 ]] && printf '%d Modul(e) waren bereits ok (Resume).\n' "$RESUMED_OK"
[[ $SKIPPED  -gt 0 ]] && printf '%d Modul(e) übersprungen.\n' "$SKIPPED"
[[ $FAILED   -gt 0 ]] && printf '%d Modul(e) fehlgeschlagen — Log: %s\n' "$FAILED" "$INSTALLER_LOG_FILE"
[[ ${INSTALLER_DRY_RUN:-0} == 1 ]] && printf 'Dry-Run — es wurde nichts geändert und kein Fortschritt gespeichert.\n'
printf 'Festplatte nachtragen:  bash install.sh --add-disk\n'
printf 'Gesundcheck:            .venv/bin/python musik.py doctor --quick\n'
[[ $FAILED -gt 0 ]] && exit 1
exit 0
