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
import time


def _outcome(root: str,
             only_new_vs: set | None = None) -> tuple[dict, list[tuple[str, str]]]:
    """Status counts + (artist, album) pairs of imported albums under root.
    only_new_vs: normcased Unit-Keys, die VOR diesem Lauf schon entschieden
    waren — deren Alben zählen nicht (Enrich-Gate, Story 9.7-Befund)."""
    from . import state as state_mod

    rk = os.path.normcase(os.path.normpath(root))
    counts: dict[str, int] = {}
    albums: list[tuple[str, str]] = []
    for key, u in sorted(state_mod.units(state_mod.load()).items()):
        k = os.path.normcase(os.path.normpath(key))
        if k != rk and not k.startswith(rk + os.sep):
            continue
        counts[u.get("status", "?")] = counts.get(u.get("status", "?"), 0) + 1
        if u.get("status") in ("auto", "asis") and not u.get("singleton") \
                and (only_new_vs is None or k not in only_new_vs):
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


def _activity(phase: str, detail: str = "") -> None:
    """Herzschlag für den Import-Monitor (Story 9.7): die aktuelle
    Phase atomar nach state/ingest-current.json schreiben — der Tab
    zeigt damit, womit der Ingest gerade beschäftigt ist. Best-Effort:
    ein fehlgeschlagenes Schreiben darf den Lauf nie brechen."""
    import json as _json

    from .paths import state_dir

    try:
        d = state_dir()
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, "ingest-current.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            _json.dump({"phase": phase, "detail": detail,
                        "updated": time.time()}, fh, ensure_ascii=False)
        os.replace(tmp, os.path.join(d, "ingest-current.json"))
    except OSError:
        pass


def _prune_empty_children(root: str, keep: set[str] = ()) -> None:
    """Remove empty child dirs below root, deepest first so emptied
    husks cascade away in one pass. The root itself and every path in
    `keep` (the other configured roots — nested roots stay anchored,
    as in the pre-10.1 pruner) are never removed. Hidden dirs are
    neither entered nor removed: MusicGrabber 4.4 creates its
    .mg_staging job dir before the first file lands, and deleting one
    mid-job would fail the download (Story 10.1)."""
    from .scan import walk_visible

    protected = {os.path.normcase(os.path.abspath(root))}
    protected.update(os.path.normcase(os.path.abspath(k)) for k in keep)
    candidates = []
    for dirpath, _dirs, _filenames in walk_visible(root):
        if os.path.normcase(os.path.abspath(dirpath)) not in protected:
            candidates.append(dirpath)
    for dirpath in sorted(candidates, key=len, reverse=True):
        try:
            os.rmdir(dirpath)  # succeeds only when empty
        except OSError:
            pass


def _scene_packaging_junk(root: str) -> list[str]:
    """Scene-packaging files (.nfo/.sfv/.log/.m3u/.txt) below root,
    outside hidden directories — inside .mg_staging they belong to a
    running MusicGrabber job and must stay (Story 10.1)."""
    from .scan import is_audio, walk_visible

    junk = []
    for dirpath, _dirs, filenames in walk_visible(root):
        junk += [os.path.join(dirpath, f) for f in filenames
                 if not is_audio(f)
                 and f.lower().endswith(('.nfo', '.sfv', '.log', '.m3u', '.txt'))]
    return junk


def cmd_ingest(root: str | None = None) -> int:
    # Spooled Monitor-Aktionen zuerst (Story 9.6): hier läuft der ingest.lock
    # bereits (systemd-flock oder Bot-Executor) — der Ingest bleibt die
    # einzige schreibende Instanz und liefert die echten Ergebnisse in die
    # Job-Records, statt dass Aktionen an Dauerbetrieb abprallen.
    from . import spool as spool_mod

    spool_mod.drain_and_execute(log=print)
    _activity("start")
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
    # Imported units MOVE their files away — empty husk dirs would pile
    # up in the dropzone forever (keep_root protects them as MG layout
    # anchors). Prune empty CHILD dirs everywhere; the roots themselves
    # stay (SMB drop targets must exist between timer runs) and
    # ensure_staging_layout() below re-anchors the MusicGrabber root
    # (Albums/Playlists/Singles).
    root_set = {os.path.normcase(os.path.abspath(r)) for r in roots}
    for r in roots:
        _prune_empty_children(r, keep=root_set)
    # MG's downloader expects its layout anchors host-side (ENOENT
    # incident 2026-10-09); no-op for roots that are not MG staging
    from .musicgrabber import ensure_staging_layout
    ensure_staging_layout()
    _activity("idle")
    return rc


def _mg_playlist_plans(root: str) -> list[dict]:
    """Story 2.2: MusicGrabber playlist staging (Playlists/<Name>/) —
    the scanned units force singleton split (playlist tracks belong on
    their real albums / Singles, not as one VA album) and the playlist
    specs get prepared for the post-import build. [] on roots without a
    musicgrabber/Playlists subtree."""
    from types import SimpleNamespace

    from . import playlists as playlists_mod
    from . import state as state_mod
    from .playlists import _safe_filename

    orig_marker = os.path.normpath(
        os.path.join(root, "musicgrabber", "Playlists"))
    norm_marker = os.path.normcase(orig_marker)
    if not os.path.isdir(orig_marker):
        return []
    st = state_mod.load()
    changed = False
    dirs: dict[str, str] = {}
    for key, u in state_mod.units(st).items():
        k = os.path.normcase(os.path.normpath(key))
        if not k.startswith(norm_marker + os.sep):
            continue
        if not (u.get("singleton") or u.get("split_into_singletons")):
            u["split_into_singletons"] = True
            u.setdefault("hints", []).append("mg-playlist")
            changed = True
        rel = k[len(norm_marker) + 1:]
        ndir = norm_marker + os.sep + rel.split(os.sep)[0]
        # normcase only lowercases (same length) — the original-case dir
        # path can be cut from the raw key at the same offsets
        dirs.setdefault(ndir, orig_marker + os.sep
                        + key[len(orig_marker) + 1:].split(os.sep)[0])
    if changed:
        state_mod.save(st)
    plans = []
    for ndir, pl_dir in sorted(dirs.items()):
        prep = playlists_mod.prepare_mg(pl_dir)
        if prep is None:
            continue
        name, spec = prep
        plans.append({
            "job": SimpleNamespace(
                job_id=f"mg-{_safe_filename(name)}",
                job_dir=pl_dir,
                query="",
            ),
            "spec": spec,
            "ids": playlists_mod.snapshot_ids(),
        })
        print(f"ingest: MG playlist „{name}“ "
              f"({len(spec['entries'])} Einträge) vorgemerkt")
    return plans


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
    _activity("scan", root)
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

    # Enrich-Gate (Befund 2026-10-20): _outcome listete historisch ALLE
    # auto/asis-Units des Roots — bei 1000+ Alben lief der Enrich (~1000
    # beets-Subprozess-Paare) jeden Zyklus über 1 h, OHNE dass dieser Lauf
    # etwas importiert hatte (Dauerbetrieb; der Lock blockierte Bot,
    # Monitor-Aktionen und Waiter). Nur Units, die DIESEN Lauf entscheiden,
    # werden angereichert.
    pre_decided = {
        os.path.normcase(os.path.normpath(k))
        for k, u in state_mod.units(state_mod.load()).items()
        if u.get("status") in ("auto", "asis")
        and (k == rk or k.startswith(rk + os.sep))
    }

    # Story 2.2: MusicGrabber playlist dirs — singleton split + specs
    mg_plans = _mg_playlist_plans(root)

    print("ingest: running import (musicbrainz chain)")
    _activity("import", root)
    engine.cmd_import(only=root)

    # include_pending: staging must never linger — everything decidable
    # gets decided, tag-complete rest import on their own tags.
    print("ingest: asis fallback for review/unmatched/pending units")
    _activity("asis", root)
    asis_mod.cmd_asis(only=root, include_pending=True)

    # Story 2.2: match the imported playlist tracks, write the m3u
    pl_states = []
    if mg_plans:
        from . import playlists as playlists_mod

        for plan in mg_plans:
            pl_states.extend(playlists_mod.build(
                plan["job"], [plan["spec"]], plan["ids"]))
            print(f"ingest: {playlists_mod.summarize(pl_states[-1])}"
                  if pl_states else "ingest: playlist build leer")

    if os.path.isdir(root):
        # keep_root: the staging root is a docker bind-mount source —
        # deleting it makes docker recreate it as root and crash the
        # MusicGrabber container (PermissionError for the PUID user).
        cleanup_mod.cmd_cleanup(root=root, keep_root=True)
    os.makedirs(root, exist_ok=True)

    # Scene packaging sweep: .nfo/.sfv/.log/.m3u/.txt are import-
    # irrelevant junk (the tags carry everything) — cleanup skips dirs
    # that still hold audio (review/pending units), so their packaging
    # would linger forever and block the husk prune (live 2026-10-11:
    # 32 nfo husks after a 454-file drop). Cover images stay — they can
    # still serve as art sources.
    junk = _scene_packaging_junk(root)
    if junk:
        from . import trash as trash_mod
        trash_mod.trash_files(junk, 'source-cleanup',
                              detail='scene packaging (ingest sweep)')
        print(f"ingest: archived {len(junk)} packaging file(s) from staging")

    counts, albums = _outcome(root, only_new_vs=pre_decided)
    if albums:
        print("ingest: enriching art/genre for imported albums")
        _activity("enrich", f"{len(albums)} Album/-e")
        fetch_mod._enrich_albums(albums)

    print("ingest outcome:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    ok, msg = plex_mod.refresh_library()
    if ok and msg:
        print("ingest:", msg)
    if pl_states:
        from . import playlists as playlists_mod

        for line in playlists_mod.upload(pl_states):
            print("ingest:", line)
    return 0
