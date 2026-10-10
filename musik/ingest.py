"""`musik ingest`: import staged downloader output into the library.

The acquisition engines (MusicGrabber, PI-SETUP Phase 9) write ONLY into
staging areas — beets/musik stays the only writer of the real library.
This command runs the proven fetch import chain minus the download part
over one or more staging roots (config `musik: ingest: roots`; default:
the MusicGrabber staging only; typical addition: the Windows dropzone
`_incoming/windows`, see README "Musik vom Windows-PC"):

    scan -> gap-aware pre-pass -> MusicBrainz import -> asis fallback
         -> cleanup -> art/genre backfill -> Plex refresh

Invoked periodically by musik-ingest.timer (every 15 min) so the staging
areas stay transient and nothing enters the library unprocessed. MG's own
Playlists/*.m3u are not yet consumed (ToDo 2.2); cleanup archives them
with the emptied folders.
"""

import os


def _outcome(root: str) -> tuple[dict, list[tuple[str, str]]]:
    """Status counts + (artist, album) pairs of imported albums under root."""
    from . import state as state_mod

    rk = os.path.normcase(os.path.normpath(root))
    counts: dict[str, int] = {}
    albums: list[tuple[str, str]] = []
    for key, u in sorted(state_mod.units(state_mod.load()).items()):
        k = os.path.normcase(os.path.normpath(key))
        if k != rk and not k.startswith(rk + os.sep):
            continue
        counts[u.get("status", "?")] = counts.get(u.get("status", "?"), 0) + 1
        if u.get("status") in ("auto", "asis") and not u.get("singleton"):
            # as-is units carry identity in `guessed`/`candidates`; auto
            # album units in file_results->chosen (same logic as the
            # fetch chain's _import_job).
            c = (u.get("chosen")
                 or ((u.get("file_results") or [{}])[0].get("chosen"))
                 or (u.get("candidates") or [{}])[0]
                 or {})
            g = u.get("guessed") or {}
            album = c.get("album") or g.get("album")
            if album:
                albums.append((c.get("artist") or g.get("artist") or "", album))
    return counts, albums


def _configured_roots() -> list[str]:
    """Ingest roots from config `musik: ingest: roots` (list of paths).

    Default when unset: the MusicGrabber staging root only — existing
    setups keep their exact behavior. Typical extension: a Windows
    dropzone next to it (README "Musik vom Windows-PC").
    """
    from .paths import incoming_dir

    try:
        from beets import config as beets_config

        roots = beets_config["musik"]["ingest"]["roots"].get()
    except Exception:
        roots = None
    if isinstance(roots, str):
        roots = [roots]
    if not roots:
        return [os.path.normpath(os.path.join(incoming_dir(), "musicgrabber"))]
    return [os.path.normpath(str(r).strip()) for r in roots if str(r).strip()]


def cmd_ingest(root: str | None = None) -> int:
    if root:
        # ad-hoc single root: explicit path, never auto-created
        roots = [os.path.normpath(root)]
    else:
        roots = _configured_roots()
        # configured roots are part of the pipeline contract — they must
        # exist so SMB drops and timers always find them (the Windows
        # dropzone materializes with the first timer run)
        for r in roots:
            os.makedirs(r, exist_ok=True)
    rc = 0
    for r in roots:
        rc = _ingest_one(r) or rc
    # MG's downloader expects its layout anchors host-side (ENOENT
    # incident 2026-10-09); no-op for roots that are not MG staging
    from .musicgrabber import ensure_staging_layout
    ensure_staging_layout()
    return rc


def _ingest_one(root: str) -> int:
    from . import asis as asis_mod
    from . import cleanup as cleanup_mod
    from . import engine
    from . import fetch as fetch_mod
    from . import plex as plex_mod
    from . import scan as scan_mod
    from .scan import collect_audio_tree

    if not os.path.isdir(root) or not collect_audio_tree(root):
        print(f"ingest: staging empty — nothing to do ({root})")
        return 0

    print(f"ingest: processing {root}")
    scan_mod.cmd_scan(root)

    # The staging root persists (keep_root) and MusicGrabber reuses
    # Singles/<Artist>/ — so a decided unit can RECEIVE NEW FILES later.
    # Reopen decided units only when files are actually ON DISK (stale
    # state rows keep their historical, long-moved file lists — those
    # must stay decided). In staging, present files are by definition
    # unprocessed; gap-fill discards re-downloads of known tracks.
    from . import state as state_mod
    from .scan import openable
    rk = os.path.normcase(os.path.normpath(root))
    st = state_mod.load()
    reopened = 0
    for key, u in state_mod.units(st).items():
        k = os.path.normcase(os.path.normpath(key))
        if k != rk and not k.startswith(rk + os.sep):
            continue
        if u.get("status") not in ("asis", "auto", "duplicate", "review-apply"):
            continue
        present = [f for f in (u.get("files") or [])
                   if os.path.isfile(openable(f))]
        if present:
            u["files"] = present
            u["n_files"] = len(present)
            state_mod.set_status(u, "pending",
                                 "reopened: new files arrived in staging folder")
            reopened += 1
    if reopened:
        state_mod.save(st)
        print(f"ingest: reopened {reopened} decided unit(s) with new files")

    # Gap-aware pre-pass: album already in the library -> only missing
    # tracks stay; one-track units become singletons (Singles\ path).
    for note in fetch_mod._prepare_units(root):
        print(f"ingest: {note}")

    print("ingest: running import (musicbrainz chain)")
    engine.cmd_import(only=root)

    # include_pending: staging must never linger — everything decidable
    # gets decided, tag-complete rest import on their own tags.
    print("ingest: asis fallback for review/unmatched/pending units")
    asis_mod.cmd_asis(only=root, include_pending=True)

    if os.path.isdir(root):
        # keep_root: the staging root is a docker bind-mount source —
        # deleting it makes docker recreate it as root and crash the
        # MusicGrabber container (PermissionError for the PUID user).
        cleanup_mod.cmd_cleanup(root=root, keep_root=True)
    os.makedirs(root, exist_ok=True)

    counts, albums = _outcome(root)
    if albums:
        print("ingest: enriching art/genre for imported albums")
        fetch_mod._enrich_albums(albums)

    print("ingest outcome:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    ok, msg = plex_mod.refresh_library()
    if ok and msg:
        print("ingest:", msg)
    return 0
