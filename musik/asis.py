"""`musik asis`: file already-tagged units without a MusicBrainz match.

For review/unmatched units whose files carry complete, consistent tags
(scene rips usually do), this imports them "as-is" into the configured
layout. It is an explicit, user-invoked action — never part of the
automatic pipeline. Duplicates are still resolved by quality, cover art
and genres are still fetched, and everything is logged.
"""

import os
import re
import time

import mutagen

from .scan import openable


def _tag(f: str, field: str) -> str:
    try:
        m = mutagen.File(openable(f), easy=True)
        if m is None:
            return ""
        vals = m.get(field) or []
        return str(vals[0]).strip() if vals else ""
    except Exception:
        return ""


def from_fetch(unit: dict) -> bool:
    """Downloader staging unit (Spotify/YouTube fetch job).

    Per-track tags come from the streaming catalog and are authoritative
    per file; the album tag intentionally differs between tracks (a
    best-of playlist spans many releases). Beets groups these by album
    tag on import, landing every track in its own release's folder.
    """
    return os.path.basename(unit.get("path") or "").startswith("fetch-")


def tags_complete(unit: dict) -> tuple[bool, str]:
    """Every file needs artist/album/title; album must be consistent.

    Singleton units (chart dumps etc.) and fetch-staging units (playlists,
    multi-release downloads) carry a different release album tag per track
    by design — there the album tag is neither compared across files nor
    strictly required per file (matches the singleton behavior).
    """
    if not unit.get("files"):
        return False, "no files"
    per_track = bool(
        unit.get("singleton") or unit.get("split_into_singletons")
        or from_fetch(unit)
    )
    album = None
    for f in unit["files"]:
        if not os.path.isfile(openable(f)):
            return False, f"missing file {os.path.basename(f)}"
        artist = _tag(f, "albumartist") or _tag(f, "artist")
        title = _tag(f, "title")
        fa = _tag(f, "album")
        if not artist or not title or (not fa and not per_track):
            return False, (
                f"incomplete tags in {os.path.basename(f)} "
                f"(artist={artist!r}, album={fa!r}, title={title!r})"
            )
        if album is None:
            album = fa.lower() if fa else ""
        elif not per_track and fa and fa.lower() != album:
            return False, "inconsistent album tags across files"
    return True, ""


def enrich_from_meta_files(unit: dict) -> int:
    """Fill missing artist/title tags from the release's .nfo/.txt.

    Scene rips ship .nfo files whose tracklist ('01. Artist - Title (4:23)')
    is authoritative when the sources don't know the release and the
    files' own tags are thin. Only EMPTY fields are filled; tracks are
    matched by track number (tag, else leading filename number).
    Returns the number of files touched.
    """
    metas = [m for m in (unit.get("meta_files") or []) if os.path.isfile(m)]
    if not metas:
        return 0
    entries: dict[int, dict] = {}
    for mf in metas:
        try:
            raw = open(mf, "rb").read()
        except OSError:
            continue
        text = None
        for enc in ("utf-8", "cp437", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if not text:
            continue
        for line in text.splitlines():
            m = re.match(r"^\s{0,6}(\d{1,2})[\.\)\-]\s+(\S.*?)\s*$", line)
            if not m:
                continue
            num = int(m.group(1))
            rest = re.sub(r"\s*[\(\[][0-9:]{3,5}[\)\]]?\s*$", "", m.group(2))
            if num not in entries and rest:
                if " - " in rest:
                    artist, title = rest.split(" - ", 1)
                    entries[num] = {"artist": artist.strip(), "title": title.strip()}
                else:
                    entries[num] = {"artist": "", "title": rest.strip()}
    if not entries:
        return 0

    def track_no(f: str) -> int | None:
        vals = _tag(f, "track")
        m = re.match(r"^(\d{1,2})", vals)
        if m:
            return int(m.group(1))
        m = re.match(r"^(\d{1,2})[\s\.\-_]", os.path.basename(f))
        return int(m.group(1)) if m else None

    touched = 0
    for f in unit.get("files") or []:
        need_artist = not _tag(f, "artist") and not _tag(f, "albumartist")
        need_title = not _tag(f, "title")
        if not (need_artist or need_title):
            continue
        num = track_no(f)
        entry = entries.get(num or -1)
        if not entry:
            continue
        m = mutagen.File(openable(f), easy=True)
        if m is None:
            continue
        changed = False
        if need_artist and entry["artist"]:
            m["artist"] = entry["artist"]
            if not _tag(f, "albumartist"):
                m["albumartist"] = entry["artist"]
            changed = True
        if need_title and entry["title"]:
            m["title"] = entry["title"]
            changed = True
        if changed:
            m.save()
            touched += 1
    return touched


def _fill_empty_original_years(lib) -> int:
    """As-is imports have no MB data: derive original_year from year so
    the `$original_year` path templates work. Only fills empty fields."""
    fixed = 0
    for album in lib.albums():
        if not album.original_year and album.year:
            album.original_year = album.year
            album.store()
            fixed += 1
    for item in lib.items():
        if not item.original_year and item.year:
            item.original_year = item.year
            item.store()
            fixed += 1
    return fixed


def cmd_asis(only: str | None = None, dry_run: bool = False,
             include_pending: bool = False) -> int:
    from . import state as state_mod
    from . import trash as trash_mod
    from .engine import restrict_sources, setup_beets
    from .session import MusikSession

    # as-is imports perform no lookups — never load metadata source
    # plugins (a broken beatport4 token must not be able to kill an
    # asis run through its import_begin setup).
    restrict_sources([])
    setup_beets()
    st = state_mod.load()
    want = os.path.normcase(os.path.normpath(only)) if only else None
    statuses = ("review", "unmatched", "network")
    if include_pending:
        statuses += ("pending",)

    selected = []
    for u in state_mod.units(st).values():
        if u.get("status") not in statuses:
            continue
        if want:
            upath = os.path.normcase(os.path.normpath(u["path"]))
            if want != upath and not upath.startswith(want + os.sep):
                continue
        # stale entries (files already imported by a earlier partial run
        # of this unit) must not block the remaining files
        present = [f for f in (u.get("files") or []) if os.path.isfile(openable(f))]
        if present:
            u["files"] = present
            u["n_files"] = len(present)
        ok, _why = tags_complete(u)
        if ok:
            selected.append(u)
    selected.sort(key=lambda u: u["path"])
    print(f"asis: {len(selected)} tag-complete unit(s) eligible"
          + (" (DRY RUN — nothing done)" if dry_run else ""))
    if not selected:
        return 0

    from beets import config as beets_config
    from beets.importer.session import ImportSession
    from beets.library import Library

    lib = Library(
        beets_config["library"].as_filename(),
        beets_config["directory"].as_filename(),
    )

    # As-is items have no MB original_year; the album templates use it.
    # Swap in $year for this session, restore afterwards.
    paths_view = beets_config["paths"]
    saved_paths = {k: paths_view[k].as_str() for k in ("default", "comp", "singleton")}
    for k in saved_paths:
        paths_view[k] = saved_paths[k].replace("$original_year", "$year")

    class AsisSession(MusikSession):
        """Non-autotag session: beets' import_asis stage files everything
        with its current tags; our duplicate handling still applies."""

        def set_config(self, config) -> None:
            super().set_config(config)
            self.config["autotag"] = False

    done = 0
    try:
        for i, unit in enumerate(selected, 1):
            label = os.path.basename(unit["import_path"])
            if dry_run:
                print(f"[{i}/{len(selected)}] would-as-is  {label}")
                continue
            singletons = bool(unit.get("singleton") or unit.get("split_into_singletons"))
            session = AsisSession(lib, None, [unit["import_path"]], singletons)
            try:
                session.run()
            except KeyboardInterrupt:
                state_mod.save(st)
                print("\ninterrupted — state saved")
                return 130
            except Exception as exc:
                import traceback

                traceback.print_exc()
                state_mod.set_status(unit, "error", f"asis: {type(exc).__name__}: {exc}")
                state_mod.save(st)
                print(f"[{i}/{len(selected)}] ERROR   {label}: {exc}")
                continue
            finally:
                # set_config flipped the shared import view; restore it so
                # later regular imports keep autotagging.
                beets_config["import"]["autotag"] = True

            if session.duplicate_losers:
                trash_mod.trash_files(
                    [f for f in session.duplicate_losers if os.path.isfile(f)],
                    "duplicate", f"lost duplicate comparison (asis {unit['path']})",
                )
                trash_mod.prune_empty_dirs(session.duplicate_losers, unit["import_path"])

            from . import engine as _engine

            _engine._trash_unreadable(unit, "asis")

            unit["decision_kind"] = _engine._release_kind(unit)
            unit["decision_type"] = "own-tags"
            state_mod.set_status(unit, "asis", "imported as-is (user-invoked, tags complete)")
            state_mod.save(st)
            done += 1
            print(f"[{i}/{len(selected)}] asis     {label}")
    finally:
        for k, v in saved_paths.items():
            paths_view[k] = v

    fixed = _fill_empty_original_years(lib)
    if fixed:
        print(f"filled empty original_year on {fixed} album(s)/item(s)")
    print(f"asis: {done} unit(s) imported with their own tags")
    return 0
