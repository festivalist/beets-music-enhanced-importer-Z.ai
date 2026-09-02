"""`musik asis`: file already-tagged units without a MusicBrainz match.

For review/unmatched units whose files carry complete, consistent tags
(scene rips usually do), this imports them "as-is" into the configured
layout. It is an explicit, user-invoked action — never part of the
automatic pipeline. Duplicates are still resolved by quality, cover art
and genres are still fetched, and everything is logged.
"""

import os
import time

import mutagen


def _tag(f: str, field: str) -> str:
    try:
        m = mutagen.File(f, easy=True)
        if m is None:
            return ""
        vals = m.get(field) or []
        return str(vals[0]).strip() if vals else ""
    except Exception:
        return ""


def tags_complete(unit: dict) -> tuple[bool, str]:
    """Every file needs artist/album/title; album must be consistent."""
    if not unit.get("files"):
        return False, "no files"
    album = None
    for f in unit["files"]:
        if not os.path.isfile(f):
            return False, f"missing file {os.path.basename(f)}"
        artist = _tag(f, "albumartist") or _tag(f, "artist")
        title = _tag(f, "title")
        fa = _tag(f, "album")
        if not artist or not title or not fa:
            return False, (
                f"incomplete tags in {os.path.basename(f)} "
                f"(artist={artist!r}, album={fa!r}, title={title!r})"
            )
        if album is None:
            album = fa.lower()
        elif fa.lower() != album:
            return False, "inconsistent album tags across files"
    return True, ""


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


def cmd_asis(only: str | None = None, dry_run: bool = False) -> int:
    from . import state as state_mod
    from . import trash as trash_mod
    from .engine import setup_beets
    from .session import MusikSession

    setup_beets()
    st = state_mod.load()
    want = os.path.normcase(os.path.normpath(only)) if only else None

    selected = []
    for u in state_mod.units(st).values():
        if u.get("status") not in ("review", "unmatched", "network"):
            continue
        if want:
            upath = os.path.normcase(os.path.normpath(u["path"]))
            if want != upath and not upath.startswith(want + os.sep):
                continue
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
