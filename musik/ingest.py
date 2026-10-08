"""`musik ingest`: import staged downloader output (MusicGrabber) into the
library.

The acquisition engines (MusicGrabber, PI-SETUP Phase 9) write ONLY into
the staging area — beets/musik stays the only writer of the real library.
This command runs the proven fetch import chain minus the download part
over a staging root:

    scan -> gap-aware pre-pass -> MusicBrainz import -> asis fallback
         -> cleanup -> art/genre backfill -> Plex refresh

Invoked periodically by musik-ingest.timer (every 15 min) so the staging
area stays transient and nothing enters the library unprocessed. MG's own
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


def cmd_ingest(root: str | None = None) -> int:
    from . import asis as asis_mod
    from . import cleanup as cleanup_mod
    from . import engine
    from . import fetch as fetch_mod
    from . import plex as plex_mod
    from . import scan as scan_mod
    from .paths import incoming_dir
    from .scan import collect_audio_tree

    root = os.path.normpath(root or os.path.join(incoming_dir(), "musicgrabber"))
    if not os.path.isdir(root) or not collect_audio_tree(root):
        print(f"ingest: staging empty — nothing to do ({root})")
        return 0

    print(f"ingest: processing {root}")
    scan_mod.cmd_scan(root)

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
