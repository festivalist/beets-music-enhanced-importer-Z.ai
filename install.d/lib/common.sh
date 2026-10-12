# common.sh — gemeinsame Helfer für Treiber (install.sh) und alle Module.
# Wird von beiden Seiten gesourct; keine Nebeneffekte außer State-Laden.
#
# Konventionen (EPIC 8):
#   - Module laufen als EIGENE Prozesse (bash install.d/NN-name.sh); der
#     Treiber wertet nur den Exit-Code aus: 0=ok, 77=skip, 78/sonst=fail.
#     Ein Crash in einem Modul kann den Treiber nicht mitreißen.
#   - State = shell-sourcebare Datei ($INSTALLER_STATE_DIR/state.env):
#     ANSWER_<key>=… (Nutzerantworten, überlebt Abbrüche) und
#     MOD_<name>=ok|skip|fail (Modulfortschritt). Werte werden mit printf %q
#     geschrieben → beliebiges Runden durch source/eval ist sicher.
#   - Antworten werden NIE zweimal gefragt: ask_value liefert die
#     gespeicherte Antwort zurück (Resume-Garantie).
#   - INSTALLER_DRY_RUN=1: run() zeigt Befehle statt sie auszuführen;
#     finish() schreibt dann keinen Modulstatus (Generalprobe zählt nicht).

# --- Umgebung (Treiber setzt INSTALLER_*-Exporte; Fallbacks für Direktaufruf) --
INSTALLER_PROJECT_DIR="${INSTALLER_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export INSTALLER_PROJECT_DIR
INSTALLER_STATE_DIR="${MUSIK_INSTALLER_STATE:-${INSTALLER_STATE_DIR:-/var/lib/musik-installer}}"
INSTALLER_STATE_FILE="$INSTALLER_STATE_DIR/state.env"
INSTALLER_LOG_FILE="$INSTALLER_STATE_DIR/installer.log"

# --- Ausgabe ------------------------------------------------------------------
step() { printf '\n==> %s\n' "$1"; }
ok()   { printf '    %s\n' "$1"; }
info() { printf '    %s\n' "$1"; }
warn() { printf '    WARNUNG: %s\n' "$1" >&2; }
err()  { printf '    FEHLER: %s\n' "$1" >&2; }

log() {
    mkdir -p "$INSTALLER_STATE_DIR" 2>/dev/null || true
    printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$INSTALLER_LOG_FILE" 2>/dev/null || true
}

# --- State --------------------------------------------------------------------
# State-Laden: env-Variablen (z. B. aus --answers, vom Treiber persistiert)
# bleiben führend, weil der Treiber Antworten VOR dem Modul-Lauf in den State
# schreibt — danach ist der State die eine Wahrheit.
if [[ -r "$INSTALLER_STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$INSTALLER_STATE_FILE" || true
fi

state_get() { # KEY [default] → Wert
    local key=$1 def=${2:-} line=""
    [[ -r "$INSTALLER_STATE_FILE" ]] || { printf '%s' "$def"; return 0; }
    line=$(grep -m1 "^${key}=" "$INSTALLER_STATE_FILE" || true)
    line=${line#*=}
    if [[ -n "$line" ]]; then eval "printf '%s' $line"; else printf '%s' "$def"; fi
}

state_set() { # KEY VAL — atomar (tmp+mv), vorhandene Zeile wird ersetzt
    local key=$1 val=$2 f="$INSTALLER_STATE_FILE" tmp="$INSTALLER_STATE_FILE.tmp"
    mkdir -p "$INSTALLER_STATE_DIR" 2>/dev/null || true
    touch "$f" 2>/dev/null || { err "State-Datei nicht schreibbar: $f"; return 1; }
    { grep -v "^${key}=" "$f" 2>/dev/null || true
      printf '%s=%q\n' "$key" "$val"; } > "$tmp"
    mv "$tmp" "$f"
}

# --- Modul-Lebenszyklus -------------------------------------------------------
module_name() { # 20-disks.sh → disks (Pfad/Nummernpräfix/Extension abwerfen)
    local n
    n=$(basename "${0%.sh}")
    printf '%s' "${n#[0-9]*-}"
}

mod_set() { # name status [note]
    state_set "MOD_$1" "$2"
    if [[ $# -ge 3 && -n "$3" ]]; then state_set "MOD_${1}_note" "$3"; fi
}

finish() { # ok|skip|fail [Meldung] — Status schreiben (nicht im Dry-Run) + beenden
    local status=$1; shift
    local msg=${*:-}
    local name
    name=$(module_name)
    case "$status" in
        ok)   log "MODUL $name: ok — $msg"
              [[ ${INSTALLER_DRY_RUN:-0} == 1 ]] || mod_set "$name" ok "${msg:+$msg}"
              exit 0 ;;
        skip) log "MODUL $name: übersprungen — $msg"
              printf '    → übersprungen: %s\n' "$msg" >&2
              [[ ${INSTALLER_DRY_RUN:-0} == 1 ]] || mod_set "$name" skip "$msg"
              exit 77 ;;
        fail) log "MODUL $name: FEHLGESCHLAGEN — $msg"
              err "$msg"
              err "Fortsetzen nach Behebung:  bash install.sh --resume"
              [[ ${INSTALLER_DRY_RUN:-0} == 1 ]] || mod_set "$name" fail "$msg"
              exit 78 ;;
    esac
    err "finish(): unbekannter Status '$status'"; exit 78
}

# --- Antworten (Prompts) ------------------------------------------------------
ask_value() { # KEY "Frage" [Default] → Wert (nie zweimal fragen: State first)
    # WICHTIG: Meldungen dieser Funktion gehen nach STDERR — sie wird in
    # $(...) aufgerufen, stdout ist ausschließlich der Rückgabewert.
    local key=$1 prompt=$2 def=${3:-} cur answer suffix
    cur=$(state_get "ANSWER_$key" "")
    if [[ -n "$cur" ]]; then printf '%s' "$cur"; return 0; fi
    if [[ ${INSTALLER_NONINTERACTIVE:-0} == 1 ]]; then
        if [[ -n "$def" ]]; then
            state_set "ANSWER_$key" "$def"
            printf '    nicht-interaktiv: %s = Default %q\n' "$key" "$def" >&2
            printf '%s' "$def"; return 0
        fi
        err "nicht-interaktiv und keine Antwort für '$key' vorhanden."
        err "Liefern per --answers:  ANSWER_$key=…"
        printf ''; return 1
    fi
    suffix=""; [[ -n "$def" ]] && suffix=" [$def]"
    read -r -p "$prompt$suffix: " answer || answer=""
    answer=${answer:-$def}
    state_set "ANSWER_$key" "$answer"
    printf '%s' "$answer"
}

confirm() { # KEY "Frage" [yes|no-Default] → 0=ja
    local key=$1 q=$2 def=${3:-yes} pre answer
    pre=$(state_get "ANSWER_$key" "")
    if [[ -n "$pre" ]]; then
        case "$pre" in j|J|y|Y|ja|Ja|yes|1|true) return 0 ;; *) return 1 ;; esac
    fi
    if [[ ${INSTALLER_NONINTERACTIVE:-0} == 1 ]]; then
        state_set "ANSWER_$key" "$def"
        [[ "$def" == yes ]] && return 0 || return 1
    fi
    read -r -p "$q (j/n, Default: $([[ $def == yes ]] && echo ja || echo nein)): " answer || answer=""
    answer=${answer:-$( [[ $def == yes ]] && echo j || echo n )}
    case "$answer" in j|J|y|Y|ja|Ja|yes) answer=yes ;; *) answer=no ;; esac
    state_set "ANSWER_$key" "$answer"
    [[ "$answer" == yes ]]
}

menu_select() { # KEY "Frage" "Opt1" "Opt2" … → gewählte Option (Text)
    # Meldungen/Menü nach STDERR (Aufruf in $(…)), stdout = Ergebnis.
    local key=$1 prompt=$2; shift 2
    local opts=("$@") pre i answer
    pre=$(state_get "ANSWER_$key" "")
    if [[ -n "$pre" ]]; then
        for i in "${opts[@]}"; do [[ "$i" == "$pre" ]] && { printf '%s' "$i"; return 0; }; done
    fi
    if [[ ${INSTALLER_NONINTERACTIVE:-0} == 1 ]]; then
        state_set "ANSWER_$key" "${opts[0]}"
        printf '    nicht-interaktiv: %s = erste Option %q\n' "$key" "${opts[0]}" >&2
        printf '%s' "${opts[0]}"; return 0
    fi
    printf '    %s:\n' "$prompt" >&2
    for i in "${!opts[@]}"; do printf '      %d) %s\n' $((i+1)) "${opts[$i]}" >&2; done
    while true; do
        read -r -p "Auswahl [1-${#opts[@]}, Default 1]: " answer || answer=1
        answer=${answer:-1}
        if [[ "$answer" =~ ^[0-9]+$ ]] && (( answer >= 1 && answer <= ${#opts[@]} )); then
            break
        fi
        for i in "${opts[@]}"; do [[ "$i" == "$answer" ]] && { answer="$i"; break 2; }; done
        printf '    Ungültige Auswahl.\n' >&2
    done
    if [[ "$answer" =~ ^[0-9]+$ ]]; then answer=${opts[$((answer-1))]}; fi
    state_set "ANSWER_$key" "$answer"
    printf '%s' "$answer"
}

# --- Ausführung ----------------------------------------------------------------
confirm_destructive() { # "Beschreibung der Aktion" → 0=ausführen
    # Bewusst NICHT im State speicherbar: eine gecachte JA-Bestätigung würde
    # bei jedem Resume-Run destruktive Schritte automatisch freigeben.
    # Nicht-interaktiv geht es nur mit dem ausdrücklichen Treiber-Flag
    # --force (INSTALLER_FORCE=1) — für Test-Harnesses dokumentiert.
    local desc=$1 ans
    if [[ ${INSTALLER_NONINTERACTIVE:-0} == 1 ]]; then
        if [[ ${INSTALLER_FORCE:-0} == 1 ]]; then
            warn "nicht-interaktiv + --force: destruktiver Schritt erlaubt: $desc"
            return 0
        fi
        err "Destruktiver Schritt braucht interaktive Bestätigung: $desc"
        err "Oder bewusst: bash install.sh --force (Test/Automatisierung)."
        return 1
    fi
    printf '    !!! %s\n' "$desc" >&2
    printf '    Alle Daten darauf gehen verloren.\n' >&2
    read -r -p "    Eintippen von JA bestätigt: " ans || ans=""
    [[ "$ans" == "JA" ]]
}

run() { # Dry-Run-fähiger Befehlsaufruf: zeigt statt auszuführen
    if [[ ${INSTALLER_DRY_RUN:-0} == 1 ]]; then
        printf '    [dry-run] %s\n' "$*"
        return 0
    fi
    "$@"
}

sudocmd() { # root → direkt; sonst sudo; beides fehlend → Fehler
    if [[ $EUID -eq 0 ]]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        err "Root-Rechte nötig für: $* — weder root noch sudo verfügbar." >&2
        return 1
    fi
}

as_user() { # USER cmd… → als bestimmter Nutzer ausführen (Schreibproben)
    local u=$1; shift
    if [[ "$(id -un)" == "$u" ]]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo -u "$u" "$@"
    elif [[ $EUID -eq 0 ]]; then
        su -s /bin/bash "$u" -c "$*"
    else
        err "kann Befehl nicht als Nutzer '$u' ausführen (kein sudo, nicht root)." >&2
        return 1
    fi
}

have() { command -v "$1" >/dev/null 2>&1; }   # have ffmpeg → 0=ja
