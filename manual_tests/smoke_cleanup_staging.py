# -*- coding: utf-8 -*-
"""Smoke test for cleanup's downloader-staging skeleton rule.

Run:  python manual_tests/smoke_cleanup_staging.py
keep_root must not only spare the staging root itself but also its empty
TOP-LEVEL dirs — MusicGrabber's layout anchors (Singles/, Albums/,
Playlists/). Live incident 2026-10-09: after an ingest cleanup emptied
the staging, every MG track job died with ENOENT '/music/Singles'.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from musik import cleanup  # noqa: E402


def build(root):
    """Simulate emptied downloader staging: anchor dirs exist, one carries
    leftover packaging junk, one artist subfolder is already gone."""
    os.makedirs(os.path.join(root, "Singles", "Some Artist"), exist_ok=True)
    os.makedirs(os.path.join(root, "Albums"), exist_ok=True)
    os.makedirs(os.path.join(root, "Playlists"), exist_ok=True)
    with open(os.path.join(root, "Singles", "Some Artist", "cover.jpg"),
              "wb") as fh:
        fh.write(b"junk")


tmp = tempfile.mkdtemp(prefix="smoke-cleanup-")
try:
    staging = os.path.join(tmp, "musicgrabber")
    trash = os.path.join(tmp, "_trash")
    os.makedirs(staging)
    build(staging)

    rc = cleanup.cmd_cleanup(root=staging, trash_base=trash, keep_root=True)
    assert rc == 0
    # the root itself survives (bind-mount source)
    assert os.path.isdir(staging)
    # layout anchors survive even though they are (now) empty
    for sub in ("Singles", "Albums", "Playlists"):
        assert os.path.isdir(os.path.join(staging, sub)), sub
    # emptied artist folder and packaging junk are gone (archived)
    assert not os.path.exists(os.path.join(staging, "Singles", "Some Artist"))
    assert os.path.isdir(os.path.join(trash, "source-cleanup"))
    print("1) keep_root spares root + top-level layout anchors OK")

    # without keep_root (a normal source folder): empty dirs AND the
    # emptied root itself go away (documented behavior)
    plain = os.path.join(tmp, "plain-source")
    os.makedirs(os.path.join(plain, "Singles"))
    rc = cleanup.cmd_cleanup(root=plain, trash_base=trash)
    assert rc == 0
    assert not os.path.exists(os.path.join(plain, "Singles"))
    assert not os.path.isdir(plain)
    print("2) normal folders still cleaned fully (incl. root) OK")

    # ensure_staging_layout recreates missing anchors (host-side); with
    # incoming_dir pointed at the fixture, missing anchors come back
    from musik import musicgrabber as MG

    MG.incoming_dir = lambda: tmp
    anchors = [os.path.join(staging, s) for s in ("Singles", "Albums")]
    for a in anchors:
        shutil.rmtree(a, ignore_errors=True)
    MG.ensure_staging_layout()
    for a in anchors:
        assert os.path.isdir(a), a
    print("3) ensure_staging_layout recreates missing anchors OK")

    print("smoke_cleanup_staging: all assertions passed")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
