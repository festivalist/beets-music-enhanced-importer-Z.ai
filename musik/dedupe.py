"""Library-level duplicate cleanup (`musik dedupe`).

Groups albums/items already in the beets DB by identity keys and keeps
the best-quality copy of each group; losers are moved to _trash.
"""

import os
from collections import defaultdict

from . import quality
from . import trash as trash_mod


def _album_score(album) -> tuple:
    paths = [os.fsdecode(i.path) for i in album.items()]
    return quality.score_files(paths)


def cmd_dedupe(dry_run: bool = False,
               fingerprint: bool = False, apply: bool = False) -> int:
    from .engine import setup_beets

    setup_beets()
    from beets import config as beets_config
    from beets.library import Library

    lib = Library(
        beets_config["library"].as_filename(),
        beets_config["directory"].as_filename(),
    )

    if fingerprint:
        return _dedupe_fingerprint(lib, apply=apply)

    groups: dict[tuple, list] = defaultdict(list)
    for album in lib.albums():
        key = (
            (album.albumartist or "").lower(),
            (album.album or "").lower(),
            album.albumtype or "",
        )
        groups[key].append(album)

    trashed = 0
    for key, albums in sorted(groups.items()):
        if len(albums) < 2:
            continue
        albums.sort(key=_album_score, reverse=True)
        winner, losers = albums[0], albums[1:]
        print(
            f"duplicate group: {winner.albumartist} - {winner.album}: "
            f"keeping {quality.describe(_album_score(winner))}"
        )
        for loser in losers:
            paths = [os.fsdecode(i.path) for i in loser.items()]
            print(
                f"  loser ({quality.describe(_album_score(loser))}): {paths[:1]}..."
                f" ({len(paths)} files)"
            )
            if dry_run:
                continue
            detail = f"lost dedupe against {os.fsdecode(winner.items()[0].path) if list(winner.items()) else '?'}"
            trashed_files = trash_mod.trash_files(
                [p for p in paths if os.path.isfile(p)], "duplicate", detail
            )
            for item in loser.items():
                item.remove(with_album=False)
            loser.remove(with_items=False)
            trash_mod.prune_empty_dirs(trashed_files, os.fsdecode(lib.directory))
            trashed += len(trashed_files)

    print(
        f"dedupe {'(dry run) ' if dry_run else ''}done: {trashed} file(s) "
        f"{'would go' if dry_run else 'moved'} to _trash"
    )
    return 0


def _dedupe_fingerprint(lib, apply: bool = False) -> int:
    """Track-level dupe hunt via AcoustID (report by default, --apply to trash).

    Same recording under different metadata is invisible to the album-level
    dedupe; chroma stores acoustid_id / acoustid_fingerprint on items, so we
    can group by those. Groups spanning one album folder only are skipped
    (that is the album dedupe's job).
    """
    groups: dict[str, list] = defaultdict(list)
    no_fp = 0
    for item in lib.items():
        key = item.get("acoustid_id")
        if not key:
            fp = item.get("acoustid_fingerprint")
            if not fp:
                no_fp += 1
                continue
            # fingerprints of the same audio share long prefixes
            key = "fp:" + fp[:24]
        groups[key].append(item)

    trashed = 0
    reported = 0
    for key, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        folders = {os.path.dirname(os.fsdecode(i.path)) for i in members}
        if len(folders) < 2:
            continue  # same-album copies are the album dedupe's territory
        reported += 1
        members.sort(key=lambda i: quality.score(os.fsdecode(i.path)), reverse=True)
        winner, losers = members[0], members[1:]
        print(f"fingerprint group {key[:16]}…: "
              f"keep {winner.artist} - {winner.title} "
              f"({quality.describe(quality.score(os.fsdecode(winner.path)))})")
        for i in members:
            mark = "  keep " if i is winner else "  LOSE "
            print(f"{mark} [{i.albumartist} / {i.album}] "
                  f"{i.artist} - {i.title} "
                  f"({quality.describe(quality.score(os.fsdecode(i.path)))}) "
                  f"{os.fsdecode(i.path)}")
        if not apply:
            continue
        for loser in losers:
            path = os.fsdecode(loser.path)
            if os.path.isfile(path):
                detail = (f"lost fingerprint dedupe against "
                          f"{os.fsdecode(winner.path)}")
                trashed_files = trash_mod.trash_files([path], "duplicate", detail)
                trash_mod.prune_empty_dirs(trashed_files, os.fsdecode(lib.directory))
                trashed += len(trashed_files)
            loser.remove(with_album=False)

    print(
        f"fingerprint dedupe: {reported} cross-album group(s), {no_fp} item(s) "
        "without fingerprint skipped"
        + ("" if apply else " — report only, re-run with --apply to trash losers")
        + (f", {trashed} file(s) moved to _trash" if apply else "")
    )
    return 0
