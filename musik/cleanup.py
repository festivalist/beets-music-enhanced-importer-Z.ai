"""`musik cleanup`: tidy a source folder after a successful import.

For every subfolder of --root that contains **no audio files anymore**
(the music was moved into the library), the remaining packaging junk
(.nfo, .sfv, .m3u, logs, artwork, ...) is archived to
_trash/source-cleanup/ with a manifest row, the emptied folders are
removed, and the root itself is deleted only when nothing at all is left
in it. Folders that still hold audio (e.g. albums waiting in review)
are never touched.
"""

import os

from .scan import is_audio


def _guard(root: str) -> str | None:
    """Refuse dangerous targets; returns a reason or None if OK."""
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return f"not a folder: {root}"
    drive, tail = os.path.splitdrive(root)
    if not tail or tail in ("\\", "/"):
        return f"refusing to clean a drive root: {root}"
    home = os.path.normcase(os.path.expanduser("~"))
    if os.path.normcase(root) == home or home.startswith(os.path.normcase(root) + os.sep):
        return f"refusing: {root} contains the user profile"
    return None


def cmd_cleanup(root: str, dry_run: bool = False,
                trash_base: str | None = None) -> int:
    from . import trash as trash_mod
    from .paths import musik_config

    root = os.path.abspath(root)
    why = _guard(root)
    if why:
        print(f"cleanup: {why}")
        return 1
    lib_dir = os.path.abspath(musik_config()["trash_dir"]).rsplit(os.sep + "_trash", 1)[0]
    if os.path.normcase(lib_dir).startswith(os.path.normcase(root) + os.sep):
        print(f"cleanup: refusing - {root} contains the music library")
        return 1

    moved = removed = rounds = 0
    if dry_run:
        print(f"cleanup (dry run) of {root}")

    while True:
        rounds += 1
        if rounds > 50:
            break
        changed = False
        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            if os.path.normcase(dirpath) == os.path.normcase(root):
                continue
            try:
                entries = os.listdir(dirpath)
            except OSError:
                continue
            if any(is_audio(n) for n in entries):
                continue  # audio still here: active unit, never touch
            files = [
                os.path.join(dirpath, n) for n in entries
                if os.path.isfile(os.path.join(dirpath, n))
            ]
            if files:
                if dry_run:
                    for f in files:
                        print(f"  would archive: {f}")
                    moved += len(files)
                else:
                    trash_mod.trash_files(
                        files, "source-cleanup",
                        detail=f"leftover packaging from {root}",
                        base_dir=trash_base,
                    )
                    moved += len(files)
                    changed = True
            if not os.listdir(dirpath):
                if dry_run:
                    print(f"  would delete empty folder: {dirpath}")
                else:
                    try:
                        os.rmdir(dirpath)
                        removed += 1
                    except OSError:
                        continue
                    changed = True
        if dry_run or not changed:
            break

    # Root deletion: only when nothing at all is left inside.
    if os.path.isdir(root) and not os.listdir(root):
        if os.path.normcase(os.path.dirname(root)) == os.path.normcase(root):
            pass
        elif dry_run:
            print(f"  would delete emptied root: {root}")
        else:
            try:
                os.rmdir(root)
                removed += 1
                print(f"  deleted emptied root: {root}")
            except OSError as exc:
                print(f"  could not delete root {root}: {exc}")

    verb = "would archive" if dry_run else "archived"
    print(
        f"cleanup: {moved} file(s) {verb}, {removed} folder(s) "
        f"{'would be ' if dry_run else ''}removed"
    )
    return 0
