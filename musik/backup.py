r"""Rotating snapshots of everything musik needs to be restored (`musik snapshot`).

One ZIP per run: beets DB (consistent copy via sqlite3 backup API),
config.yaml, run state and the local source tokens. Kept in the backup
dir (default: <library>\_backups, configurable via `musik: backup_dir:`),
oldest beyond `musik: backup_keep:` are deleted.
"""

import os
import re
import sqlite3
import time
import zipfile

import yaml

from . import state as state_mod
from .paths import CONFIG_FILE, DISCOGS_TOKEN_FILE, PROJECT_DIR, musik_config

SNAPSHOT_RE = re.compile(r"^musik-snapshot-\d{8}-\d{6}\.zip$")


def _beets_paths() -> tuple[str, str]:
    """(library db path, music directory) from config.yaml."""
    with open(CONFIG_FILE, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    db = data.get("library") or os.path.join(PROJECT_DIR, "library.db")
    directory = data.get("directory") or os.path.join(os.path.expanduser("~"), "Music")
    return db, directory


def backup_dir() -> str:
    d = musik_config().get("backup_dir") or os.path.join(_beets_paths()[1], "_backups")
    os.makedirs(d, exist_ok=True)
    return d


def keep_count() -> int:
    return int(musik_config().get("backup_keep") or 10)


def _list_snapshots(d: str) -> list[str]:
    return sorted(f for f in os.listdir(d) if SNAPSHOT_RE.match(f))


def cmd_snapshot(list_only: bool = False, keep: int | None = None) -> int:
    d = backup_dir()
    if list_only:
        snaps = _list_snapshots(d)
        if not snaps:
            print("no snapshots yet in", d)
            return 0
        print(f"{len(snaps)} snapshot(s) in {d}:")
        for f in snaps:
            size = os.path.getsize(os.path.join(d, f))
            print(f"  {f}  {size / (1024 * 1024):.1f} MB")
        return 0

    db_path, _ = _beets_paths()
    if not os.path.isfile(db_path):
        print("beets library DB not found:", db_path)
        return 1

    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(d, f"musik-snapshot-{stamp}.zip")

    # Consistent DB image even while beets has the original open.
    # (sqlite3's context manager only manages transactions, not closing.)
    db_copy = dest + ".db"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(db_copy)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()

    extras = []
    for p in (CONFIG_FILE, DISCOGS_TOKEN_FILE,
              os.path.join(PROJECT_DIR, "beatport_token.json"),
              state_mod.state_file()):
        if os.path.isfile(p):
            extras.append(p)

    try:
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(db_copy, "beets-library.db")
            for p in extras:
                z.write(p, os.path.basename(p))
    finally:
        if os.path.isfile(db_copy):
            os.remove(db_copy)

    size = os.path.getsize(dest)
    print(f"snapshot written: {dest} ({size / (1024 * 1024):.1f} MB)")

    keep_n = keep if keep is not None else keep_count()
    snaps = _list_snapshots(d)
    for old in snaps[:-keep_n] if keep_n > 0 else []:
        os.remove(os.path.join(d, old))
        print("rotated away:", old)
    print(f"({min(len(snaps), keep_n)} of {len(snaps)} kept, limit {keep_n})")
    return 0
