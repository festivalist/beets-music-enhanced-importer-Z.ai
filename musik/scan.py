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

# Mirrors beets' own multi-disc collapsing patterns (plus 'lp' for
# double-vinyl rips like 'Artist - Album [US Vinyl 2LP]\LP1').
MULTIDISC_RE = re.compile(
    r"^(.*(?:dis[ck]|cd|cassette|digital\s+media|vinyl|lp)[\W_]*)\d$", re.I
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


def readable_file(path: str) -> bool:
    """False for corrupt/unparseable audio (e.g. 'can't sync to MPEG
    frame'). Such a file can never be imported; scan excludes it from
    the unit and the engine archives it to _trash/corrupt."""
    try:
        return mutagen.File(openable(path)) is not None
    except Exception:
        return False


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
BARE_YEAR_RE = re.compile(r"(?<![0-9])((?:19|20)\d{2})(?![0-9])")

# Scene-name noise: catalog numbers in parens, media keywords, bare years,
# and pure numbers — the tail of 'Artist-Album-(CAT)-WEB-2026-GROUP'.


def _scene_noise(tok: str) -> bool:
    t = tok.strip()
    if not t:
        return True
    if t[0] in "([" and t[-1] in ")]":
        return True  # catalog number, media note
    tl = t.lower()
    if re.fullmatch(r"(?:19|20)\d{2}", tl):
        return True
    if re.fullmatch(r"\d{1,2}", tl):
        return True
    if tl in {
        "web", "single", "ep", "lp", "cdep", "cds", "cd", "vls", "sat",
        "promo", "vinyl", "dvd", "cable", "7inch", "12inch", "7", "12",
        "remixes", "deluxe", "limited", "edition", "reissue", "int",
        "front", "back",
    }:
        return True
    return False


def _clean_scene_album(album_part: str) -> str:
    """'Arriba-(TIPSY083)-SINGLE-WEB-2026-iDC' -> 'Arriba'."""
    toks = [t for t in album_part.replace("_", " ").split("-") if t.strip()]
    keep = []
    for t in toks:
        if _scene_noise(t):
            break
        keep.append(t.strip())
    return " ".join(keep).strip()


def guess_year(path: str) -> int | None:
    base = os.path.basename(os.path.normpath(path))
    m = YEAR_RE.search(base)
    if m:
        return int(m.group(1))
    m = BARE_YEAR_RE.search(base)
    return int(m.group(1)) if m else None


def parse_folder_guess(path: str) -> dict:
    """Extract 'Artist - Album' from a folder name.

    Handles two shapes:
    - '0701. Slint - Spiderland (1991)' — plain display names
    - scene dumps: '1783-Severe-(SL009)-WEB-2026-PTC',
      '2HOT2PLAY__Armin_Hermann_-_Arriba-(TIPSY083)-SINGLE-WEB-2026-iDC'
      (underscores read as spaces, media/catalog tail stripped)
    """
    base = os.path.basename(os.path.normpath(path))
    # '1958 - GREATEST HITS • Doris Day - Greatest Hits [US Vinyl Mono LP]'
    # (checked on the raw name: the numeric-prefix strip below would eat
    # the year and break the anchor)
    m = re.match(
        r"^\s*(\d{4})\s*-\s*.*?\u2022\s*(.+?)\s*[-\u2013\u2014]\s*(.+?)\s*"
        r"(?:\[[^\]]*\])?\s*$",
        base,
    )
    if m:
        return {"artist": m.group(2).strip(), "album": m.group(3).strip()}
    base = YEAR_RE.sub("", base)
    base = re.sub(r"^\s*\d+[\.\s]+", "", base).strip()
    if " - " in base:
        artist, album = base.split(" - ", 1)
        return {"artist": artist.strip().replace("_", " ").strip(),
                "album": _clean_scene_album(album)}
    flat = base.replace("_", " ")
    toks = [t for t in flat.split("-") if t.strip()]
    if len(toks) >= 2:
        album_toks = []
        for t in toks[1:]:
            if _scene_noise(t):
                break
            album_toks.append(t.strip())
        if album_toks:
            return {"artist": toks[0].strip(), "album": " ".join(album_toks)}
    return {"artist": "", "album": base.strip()}


def make_unit(path: str, import_path: str, files: list[str], kind: str,
              source: str = "scan") -> dict:
    # Corrupt files never enter the unit: beets would error the whole
    # import task on them; the engine trashes them after the run.
    good: list[str] = []
    bad: list[str] = []
    for f in files:
        (good if readable_file(f) else bad).append(f)
    files = good
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
        "unreadable_files": [os.path.normpath(f) for f in bad],
        "status": "pending" if n else "ignored",
        "reason": "" if n else (
            "all audio files unreadable (corrupt)" if bad
            else "no audio files found (cue-only rip?)"
        ),
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
            # Only audio-holding subdirs count for the multi-disc check:
            # an 'Artwork' sibling must not block an LP1/LP2 collapse.
            audio_subs = [s for s in subdirs if audio_files_in(s)]
            matched = [MULTIDISC_RE.match(os.path.basename(s)) for s in audio_subs]
            if (
                audio_subs
                and all(matched)
                and len({m.group(1).lower() for m in matched}) == 1
            ):
                # One multi-disc album: import the parent so beets collapses.
                nested = []
                for s in audio_subs:
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
                      "guessed", "unreadable_files"):
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
    corrupt = sum(
        1 for u in existing.values() for f in (u.get("unreadable_files") or [])
        if os.path.isfile(f)
    )
    if corrupt:
        print(f"corrupt audio files excluded from units: {corrupt} "
              "(archived to _trash/corrupt after their unit's import)")
    return 0
