"""Displaced-file flow: move losers to _trash/<reason>/ with a manifest.

Nothing is ever deleted outright — every displaced file keeps a row in
_trash/manifest.csv so it can be audited and restored.
"""

import csv
import os
import shutil
import time

from . import paths

MANIFEST_HEADER = [
    "timestamp", "reason", "original_path", "trash_path", "detail",
]


def manifest_file() -> str:
    return os.path.join(paths.trash_dir(), "manifest.csv")


def trash_files(files: list[str], reason: str, detail: str = "") -> list[str]:
    """Move files into _trash/<reason>/<stamp>-<n>/ and append the manifest."""
    if not files:
        return []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest_root = os.path.join(paths.trash_dir(), reason, stamp)
    os.makedirs(dest_root, exist_ok=True)

    moved = []
    used = set()
    for f in files:
        if not os.path.isfile(f):
            continue
        base = os.path.basename(f)
        target = os.path.join(dest_root, base)
        i = 1
        while target.lower() in used or os.path.exists(target):
            stem, ext = os.path.splitext(base)
            target = os.path.join(dest_root, f"{stem}-{i}{ext}")
            i += 1
        shutil.move(f, target)
        used.add(target.lower())
        moved.append((f, target))

    if moved:
        mf = manifest_file()
        new = not os.path.isfile(mf)
        with open(mf, "a", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(MANIFEST_HEADER)
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            for orig, dest in moved:
                w.writerow([ts, reason, orig, dest, detail])

    return [dest for _orig, dest in moved]


def prune_empty_dirs(files: list[str], stop_at: str) -> None:
    """Remove now-empty directories above the moved files, up to stop_at."""
    stop_at = os.path.normcase(os.path.normpath(stop_at))
    seen = set()
    for f in files:
        d = os.path.dirname(os.path.abspath(f))
        while d and os.path.normcase(d) != stop_at and d not in seen:
            seen.add(d)
            try:
                if os.listdir(d):
                    break
                os.rmdir(d)
            except OSError:
                break
            d = os.path.dirname(d)
