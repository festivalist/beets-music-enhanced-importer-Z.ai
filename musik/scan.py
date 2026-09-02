"""Pre-scan: walk the library and classify it into import units.

A *unit* is the smallest thing musik tries to identify as a whole:
- `album`     — one directory of audio files (imported as a grouped album)
- `multidisc` — a directory whose subdirectories are all CD/Disc-N style
                (imported via the parent so beets collapses the discs)
- `loose`     — a single audio file imported as a singleton
- `playlist`  — audio files referenced by an m3u/m3u8 (singletons; the
                playlist file itself is never touched)

Heuristics only steer the import; every unit's identity is still decided
by the autotagger. Nothing is moved during a scan.
"""

import os
import re
from collections import Counter

import mutagen

from . import state as state_mod

AUDIO_EXTS = {
    ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav",
    ".aiff", ".aif", ".ape", ".wma", ".wv", ".mpc", ".asf", ".m4b",
}
PLAYLIST_EXTS = {".m3u", ".m3u8"}

# Mirrors beets' own multi-disc collapsing patterns.
MULTIDISC_RE = re.compile(
    r"^(.*(?:dis[ck]|cd|cassette|digital\s+media|vinyl)[\W_]*)\d$", re.I
)
VINYL_HINT_RE = re.compile(r"(?i)(side\s*[ab]|vinyl|[abcd][1-9]\b)")
ONETOONE_LONG_SECONDS = 1200  # a single file this long is likely a live dump

junk_files: list[str] = []


def is_audio(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in AUDIO_EXTS


def openable(path: str) -> str:
    """Windows long-path-safe path (mirrors beets' util.syspath)."""
    p = os.path.abspath(path)
    if os.name == "nt" and len(p) > 240 and not p.startswith("\\\\?\\"):
        p = "\\\\?\\" + p
    return p


def audio_files_in(d: str) -> list[str]:
    try:
        names = os.listdir(d)
    except OSError:
        return []
    return sorted(
        os.path.join(d, n) for n in names if os.path.isfile(os.path.join(d, n)) and is_audio(n)
    )


def subdirs_of(d: str) -> list[str]:
    try:
        names = os.listdir(d)
    except OSError:
        return []
    return sorted(
        os.path.join(d, n) for n in names if os.path.isdir(os.path.join(d, n))
    )


def file_duration(path: str) -> float | None:
    try:
        m = mutagen.File(openable(path))
        if m is not None and m.info.length:
            return float(m.info.length)
    except Exception:
        pass
    return None


def tag_of(path: str, field: str) -> str:
    try:
        m = mutagen.File(openable(path), easy=True)
        if m is None:
            return ""
        vals = m.get(field) or []
        return str(vals[0]).strip() if vals else ""
    except Exception:
        return ""


def artist_values(files: list[str]) -> list[str]:
    """Per-file albumartist tags (falling back to artist), lowercased."""
    out = []
    for f in files:
        a = tag_of(f, "albumartist") or tag_of(f, "artist")
        out.append(a.lower().strip())
    return out


def should_split(files: list[str], kind: str) -> bool:
    """True when a directory very likely holds tracks from many artists.

    Conservative: a collapsed multi-disc dir is never split; untagged
    folders stay album units (a wrong album guess lands in review, but a
    wrongly split album would scatter to Singles).
    """
    if kind in ("multidisc", "loose", "playlist"):
        return False
    n = len(files)
    if n < 4:
        return False
    tags = artist_values(files)
    tagged = [t for t in tags if t]
    if len(tagged) < 0.6 * n:
        return False  # mostly untagged -> try as album, review decides
    distinct = len(set(tagged))
    top_share = Counter(tagged).most_common(1)[0][1] / len(tagged)
    return distinct >= 3 and top_share < 0.5


YEAR_RE = re.compile(r"\((\d{4})\)")


def guess_year(path: str) -> int | None:
    m = YEAR_RE.search(os.path.basename(os.path.normpath(path)))
    return int(m.group(1)) if m else None


def parse_folder_guess(path: str) -> dict:
    """Extract 'Artist - Album' from a folder name like
    '0701. Slint - Spiderland (1991)'."""
    base = os.path.basename(os.path.normpath(path))
    base = YEAR_RE.sub("", base)
    base = re.sub(r"^\s*\d+[\.\s]+", "", base).strip()
    if " - " in base:
        artist, album = base.split(" - ", 1)
        return {"artist": artist.strip(), "album": album.strip()}
    return {"artist": "", "album": base.strip()}


def make_unit(path: str, import_path: str, files: list[str], kind: str,
              source: str = "scan") -> dict:
    durs = [file_duration(f) for f in files]
    total = sum(d for d in durs if d)
    hints = []
    n = len(files)
    if n == 1 and total >= ONETOONE_LONG_SECONDS:
        hints.append("onefile-live")
    if 1 < n <= 4 and (
        any(VINYL_HINT_RE.search(os.path.basename(f)) for f in files)
        or (durs and total / max(n, 1) >= 480)
    ):
        hints.append("vinyl")
    split_hint = should_split(files, kind)
    if split_hint:
        hints.append("multi-artist-dir")
    seen = sorted(set(artist_values(files)) - {""})[:10]
    unit = {
        "path": os.path.normpath(path),
        "import_path": os.path.normpath(import_path),
        "files": [os.path.normpath(f) for f in files],
        "n_files": n,
        "total_duration": round(total, 1) if total else None,
        "kind": kind,
        "source": source,
        "singleton": kind in ("loose", "playlist"),
        "split_into_singletons": split_hint,
        "hints": hints,
        "artists_seen": seen,
        "year_guess": guess_year(import_path),
        "guessed": parse_folder_guess(import_path),
        "status": "pending" if n else "ignored",
        "reason": "" if n else "no audio files found (cue-only rip?)",
    }
    return unit


def parse_playlist(pfile: str, root: str) -> tuple[list[str], list[str]]:
    """Return (existing targets, missing entries) referenced by a playlist."""
    found, missing = [], []
    try:
        with open(pfile, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return [], []
    base = os.path.dirname(pfile)
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        target = os.path.normpath(
            os.path.join(base, line) if not os.path.isabs(line) else line
        )
        if os.path.isfile(target) and is_audio(target):
            found.append(target)
        else:
            missing.append(line)
    return found, missing


def classify(root: str) -> tuple[list[dict], list[str]]:
    """Walk `root` and produce units. Returns (units, notes)."""
    root = os.path.abspath(root)
    notes: list[str] = []
    units: list[dict] = []
    junk_files.clear()

    def visit(d: str) -> None:
        files = audio_files_in(d)
        subdirs = subdirs_of(d)
        note_side_files(d, units, notes)

        if files:
            units.append(make_unit(d, d, files, "album"))
            # Nested audio dirs (bonus discs inside an album dir) get
            # their own units.
            for s in subdirs:
                visit(s)
            return

        if subdirs:
            matched = [MULTIDISC_RE.match(os.path.basename(s)) for s in subdirs]
            if all(matched) and len({m.group(1).lower() for m in matched}) == 1:
                # One multi-disc album: import the parent so beets collapses.
                nested = []
                for s in subdirs:
                    nested.extend(collect_audio_tree(s))
                units.append(make_unit(d, d, nested, "multidisc"))
                return
            for s in subdirs:
                visit(s)
            return

        # Nothing audio-related here beyond what note_side_files recorded.
        return

    visit(root)

    # Every file must belong to exactly one unit: playlist singletons win
    # over album grouping for their referenced files.
    playlist_files = {
        os.path.normcase(f)
        for u in units if u["kind"] == "playlist"
        for f in u["files"]
    }
    if playlist_files:
        for u in units:
            if u["kind"] == "playlist":
                continue
            remaining = [
                f for f in u["files"]
                if os.path.normcase(f) not in playlist_files
            ]
            if len(remaining) != len(u["files"]):
                if remaining:
                    u["files"] = remaining
                    u["n_files"] = len(remaining)
                else:
                    u["dropped"] = True
        units = [u for u in units if not u.get("dropped")]

    # Root itself may hold loose audio files (handled by visit via files branch).
    return units, notes


def note_side_files(d: str, units: list[dict], notes: list[str]) -> None:
    """Record playlists (as playlist units) and junk files in directory d.

    A playlist referencing files in its OWN directory is release
    packaging (scene .m3u next to the tracks) and is ignored — the
    directory forms an album unit. Only references to files elsewhere
    become playlist singletons (genuine mixtapes).
    """
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return
    for name in names:
        full = os.path.join(d, name)
        if not os.path.isfile(full):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in PLAYLIST_EXTS:
            targets, missing = parse_playlist(full, d)
            for t in targets:
                if os.path.dirname(t) == d:
                    continue
                units.append(
                    make_unit(t, t, [t], "playlist", source=f"playlist:{full}")
                )
            if missing:
                notes.append(f"playlist {full}: {len(missing)} entries missing")
        elif ext and ext not in AUDIO_EXTS and name.lower() not in (
            "desktop.ini", "thumbs.db",
        ):
            junk_files.append(full)


def collect_audio_tree(d: str) -> list[str]:
    out = []
    for cur, _dirs, files in os.walk(d):
        out.extend(os.path.join(cur, f) for f in files if is_audio(f))
    return sorted(out)


def cmd_scan(root: str) -> int:
    from . import report as report_mod

    new_units, notes = classify(root)

    st = state_mod.load()
    existing = state_mod.units(st)

    # Drop stale pending/ignored units under the scanned root that the
    # new classification no longer produces (e.g. after a rule change)
    # and whose files are covered by new units or gone from disk.
    root_key = os.path.normcase(os.path.normpath(root))
    new_keys = {os.path.normcase(os.path.normpath(u["path"])) for u in new_units}
    covered = {
        os.path.normcase(f)
        for u in new_units for f in u.get("files", [])
    }
    removed = 0
    for k in list(existing.keys()):
        u = existing[k]
        if not (k.startswith(root_key + os.sep) or k == root_key):
            continue
        if u.get("status") not in ("pending", "ignored"):
            continue
        if k in new_keys:
            continue
        # Superseded: its files are now owned by new units — or gone.
        superseded = any(
            os.path.normcase(f) in covered for f in u.get("files", [])
        )
        gone = u.get("files") and not all(os.path.isfile(f) for f in u["files"])
        if superseded or gone:
            del existing[k]
            removed += 1

    kept, added = 0, 0
    for u in new_units:
        key = os.path.normcase(os.path.normpath(u["path"]))
        if key in existing:
            old = existing[key]
            # Refresh scan facts, keep everything the engine learned.
            for k in ("files", "n_files", "total_duration", "hints",
                      "artists_seen", "import_path", "kind", "source",
                      "singleton", "split_into_singletons", "year_guess",
                      "guessed"):
                if k in u:
                    old[k] = u[k]
            # A newly-detected dead unit (e.g. cue-only rip) that never
            # went through an import gets retired.
            if u.get("status") == "ignored" and old.get("status") == "pending":
                old["status"] = "ignored"
                old["reason"] = u.get("reason", "")
            old.setdefault("status", "pending")
            kept += 1
        else:
            existing[key] = u
            added += 1

    st.setdefault("meta", {})["last_scan"] = {
        "root": os.path.normpath(root),
        "notes": notes,
        "junk_count": len(junk_files),
    }
    state_mod.save(st)

    report_mod.write_scan_report(st, notes)
    c = state_mod.counts(st)
    print(f"scan: {added} new units, {kept} known, {removed} stale removed (root: {root})")
    print("unit status counts:", ", ".join(f"{k}={v}" for k, v in sorted(c.items())))
    for n in notes:
        print("note:", n)
    if junk_files:
        print(f"non-audio files recorded: {len(junk_files)} (see scan report)")
    return 0
