"""Library health check (`musik doctor`).

Report-only by default; writing happens only with --fix:
- dead DB rows (file gone) — removed with --fix
- orphan audio files under the library root that no DB row knows
- bitrot: FLAC decode-tested against their internal MD5 via flac.exe,
  other formats via fpcalc when chroma has no stored fingerprint;
  passes are cached by (mtime, size) and --quick skips unchanged files
- albums without art / genre counts (backfilled with --fix)
- items whose paths are near the Windows MAXPATH limit
"""

import os
import subprocess
import sys
import time

from . import state as state_mod
from .paths import BIN_DIR, FPCALC, PROJECT_DIR, reports_dir
from .scan import openable

FLAC_EXE = os.path.join(BIN_DIR, "flac.exe")
LONG_PATH_LIMIT = 240
BEETS_ENV = {**os.environ, "BEETSDIR": PROJECT_DIR}


def _open_library():
    from .engine import setup_beets

    setup_beets()
    from beets import config as beets_config
    from beets.library import Library

    return Library(
        beets_config["library"].as_filename(),
        beets_config["directory"].as_filename(),
    )


def _decode_test(exe: str, args: list[str], path: str) -> str | None:
    """Run a decode-tool on one file; None = ok, else a short error."""
    try:
        r = subprocess.run(
            [exe, *args, openable(path)],
            capture_output=True, text=True, errors="replace",
        )
    except OSError as e:
        return str(e)
    if r.returncode == 0:
        return None
    out = (r.stderr or r.stdout or "").strip().replace("\n", " ")
    return (out or f"exit code {r.returncode}")[:200]


def _cache_key(path: str) -> str:
    try:
        st = os.stat(path)
        return f"{int(st.st_mtime)}:{st.st_size}"
    except OSError:
        return ""


def check_audio(items, ok_cache: dict, quick: bool) -> tuple[list[str], list[str], dict]:
    """Decode-test library files. Returns (corrupt, skipped_notes, new_cache)."""
    if not os.path.isfile(FLAC_EXE):
        print("note: bin\\flac.exe missing — re-run install.bat to enable "
              "FLAC bitrot checks")
    corrupt: list[str] = []
    notes: list[str] = []
    new_cache: dict = {}
    checked = skipped = 0
    for item in items:
        path = os.fsdecode(item.path)
        if not os.path.isfile(path):
            continue
        key = _cache_key(path)
        cached = ok_cache.get(os.path.normcase(path))
        if cached and key and cached == key and quick:
            new_cache[os.path.normcase(path)] = cached
            skipped += 1
            continue
        ext = os.path.splitext(path)[1].lower()
        err = None
        if ext == ".flac":
            if os.path.isfile(FLAC_EXE):
                err = _decode_test(FLAC_EXE, ["-t", "--totally-silent"], path)
            # without flac.exe: no FLAC coverage (note printed once)
        elif item.get("acoustid_fingerprint"):
            # decoded fine at import; only re-test when changed since the
            # last pass (mtime/size differ from the cache)
            if not (cached and key and cached == key) and os.path.isfile(FPCALC):
                err = _decode_test(FPCALC, [], path)
        elif os.path.isfile(FPCALC):
            # chroma stored no fingerprint -> never fully decoded anywhere
            err = _decode_test(FPCALC, [], path)
        else:
            notes.append(path)
        checked += 1
        if err:
            corrupt.append(f"{path} — {err}")
            print(f"  CORRUPT: {path} — {err}")
        else:
            if key:
                new_cache[os.path.normcase(path)] = key
        if checked % 250 == 0:
            print(f"  ... {checked} files decode-tested, {len(corrupt)} corrupt so far")
    if notes:
        print(f"note: {len(notes)} non-FLAC file(s) without fingerprint skipped "
              "(fpcalc missing)")
    print(f"audio decode test: {checked} tested, {skipped} skipped via cache "
          f"(--quick), {len(corrupt)} corrupt")
    return corrupt, notes, new_cache


def find_orphans(directory: str, db_paths: set[str]) -> tuple[list[str], list[str]]:
    """Audio files the DB doesn't know, split into true orphans and
    files sitting in the `unsorted` drop zone (incoming, not yet imported).
    """
    from .scan import is_audio

    trash = os.path.normcase(os.path.join(directory, "_trash") + os.sep)
    unsorted_ = os.path.normcase(os.path.join(directory, "unsorted") + os.sep)
    orphans: list[str] = []
    incoming: list[str] = []
    for dirpath, dirnames, filenames in os.walk(directory):
        norm = os.path.normcase(dirpath + os.sep)
        if norm.startswith(trash):
            dirnames[:] = []
            continue
        bucket = incoming if norm.startswith(unsorted_) else orphans
        for name in filenames:
            if not is_audio(name):
                continue
            full = os.path.normcase(os.path.abspath(os.path.join(dirpath, name)))
            if full not in db_paths:
                bucket.append(os.path.join(dirpath, name))
    return orphans, incoming


def _backfill(what: str, args: list[str]) -> str | None:
    """Run a beets CLI backfill (fetchart/lastgenre) in a fresh process."""
    print(f"backfill: beets {' '.join(args)} ...")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "beets", *args],
            env=BEETS_ENV, capture_output=True, text=True,
            errors="replace", timeout=3600,
        )
    except subprocess.TimeoutExpired:
        return f"{what} backfill timed out"
    if r.returncode != 0:
        return f"{what} backfill failed: {(r.stderr or r.stdout or '')[:300]}"
    return None


def cmd_doctor(fix: bool = False, quick: bool = False, limit: int | None = None) -> int:
    from .fetch import tool_versions

    tools = tool_versions()
    for name, ver in tools.items():
        print(f"fetch tool {name}: {ver if ver else 'MISSING'}")

    lib = _open_library()
    items = list(lib.items())
    albums = list(lib.albums())

    audio_items = items
    audio_note = ""
    if limit and limit < len(items):
        step = max(1, len(items) // limit)
        audio_items = items[::step][:limit]
        audio_note = f"decode test limited to {len(audio_items)} of {len(items)} files (spot check)"

    dead: list[tuple[int, str]] = []  # (item id, printable path)
    long_paths: list[str] = []
    db_paths: set[str] = set()
    for item in items:
        path = os.fsdecode(item.path)
        if len(path) > LONG_PATH_LIMIT:
            long_paths.append(path)
        if os.path.isfile(path):
            db_paths.add(os.path.normcase(os.path.abspath(path)))
        else:
            dead.append((item.id, f"{path}  ({item.artist} - {item.title})"))

    orphans, incoming = find_orphans(os.fsdecode(lib.directory), db_paths)

    missing_art = [a for a in albums
                   if not a.artpath or not os.path.isfile(os.fsdecode(a.artpath))]
    missing_genre = [a for a in albums if not getattr(a, "genres", None)]

    ok_cache = (state_mod.load().get("meta") or {}).get("doctor_ok") or {}
    corrupt, skip_notes, new_cache = check_audio(audio_items, ok_cache, quick)

    # persist the pass-cache (only files seen healthy this run survive)
    st = state_mod.load()
    st.setdefault("meta", {})["doctor_ok"] = new_cache
    st.setdefault("meta", {})["doctor_last_run"] = time.time()
    state_mod.save(st)

    fixed: list[str] = []
    if fix:
        for iid, _ in dead:
            item = lib.get_item(iid)
            if item is not None:
                item.remove(delete=False)
        if dead:
            fixed.append(f"removed {len(dead)} dead DB row(s)")
        err = _backfill("fetchart", ["fetchart", "artpath:"]) if missing_art else None
        if err:
            fixed.append(err)
        elif missing_art:
            fixed.append(f"fetchart backfill run for {len(missing_art)} album(s)")
        # no -f: without it lastgenre only fills albums that have NO genre
        # (with -f it force-overwrites and WIPES genres when last.fm has
        # no page for an album — burned us once, see tools/restore_genres…)
        err = _backfill("lastgenre", ["lastgenre", "genre:"]) if missing_genre else None
        if err:
            fixed.append(err)
        elif missing_genre:
            fixed.append(f"lastgenre backfill run for {len(missing_genre)} album(s)")

    problems = (len(dead) + len(orphans) + len(corrupt)
                + len(missing_art) + len(missing_genre))
    lines = [
        "# Doctor report",
        "",
        f"Run: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        f"{' (quick)' if quick else ''}{' (fix)' if fix else ''}",
        "",
        "| check | result |", "|---|---|",
        f"| items / albums | {len(items)} / {len(albums)} |",
        f"| dead DB rows (file gone) | {len(dead)} |",
        f"| orphan audio files (no DB row) | {len(orphans)} |",
        f"| incoming files in unsorted\\ (not yet imported) | {len(incoming)} |",
        f"| corrupt files (decode test) | {len(corrupt)} |",
        f"| albums missing art | {len(missing_art)} |",
        f"| albums missing genre | {len(missing_genre)} |",
        f"| items over {LONG_PATH_LIMIT} chars | {len(long_paths)} |",
    ]
    for name, ver in tools.items():
        lines.append(f"| fetch tool {name} | {ver if ver else 'MISSING (musik fetch disabled — re-run install)'} |")
    if audio_note:
        lines.append(f"| {audio_note} | - |")
    if fix:
        lines += ["", "## Fix actions", ""]
        lines += [f"- {f}" for f in fixed] or ["- nothing needed fixing"]

    def listing(title: str, entries: list, cap: int = 50) -> None:
        nonlocal lines
        if not entries:
            return
        lines += ["", f"## {title} ({len(entries)})", ""]
        lines += [f"- `{e}`" for e in entries[:cap]]
        if len(entries) > cap:
            lines.append(f"- ... and {len(entries) - cap} more")

    listing("Dead DB rows", dead)
    listing("Orphan audio files", orphans)
    if incoming:
        lines += ["", f"## Incoming files in unsorted\\ — not yet imported "
                      f"({len(incoming)})", "",
                  "Run `musik scan --root \"<library>\\unsorted\"` + import to process these."]
        lines += [f"- `{e}`" for e in incoming[:15]]
        if len(incoming) > 15:
            lines.append(f"- ... and {len(incoming) - 15} more")
    listing("Corrupt files", corrupt)
    listing("Albums missing art", [f"{a.albumartist} - {a.album}" for a in missing_art])
    listing("Albums missing genre", [f"{a.albumartist} - {a.album}" for a in missing_genre])
    listing(f"Paths over {LONG_PATH_LIMIT} chars", long_paths)

    path = os.path.join(reports_dir(), "doctor-report.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"\ndoctor: {problems} issue(s) found"
          f"{'' if fix else ' (report only — use --fix to repair)'}")
    print("doctor report:", path)
    return 0
