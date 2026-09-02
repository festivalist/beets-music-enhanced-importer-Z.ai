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


def cmd_dedupe(dry_run: bool = False) -> int:
    from .engine import setup_beets

    setup_beets()
    from beets import config as beets_config
    from beets.library import Library

    lib = Library(
        beets_config["library"].as_filename(),
        beets_config["directory"].as_filename(),
    )

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
