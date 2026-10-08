# -*- coding: utf-8 -*-
"""Smoke test for the tier-3 own-metadata gate (musik/session.py).

Run:  python manual_tests/smoke_tier3.py
Pure logic: tag readers are monkeypatched, "files" are empty dummies —
no beets lookups, no network, temp-isolated.

Covers the 2026-10-08 fetch-staging change (EPIC 4.2): downloader staging
units skip the folder-agreement corroboration because their folder name is
job metadata and playlist tracks span releases by design.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp()

from musik import asis as asis_mod   # noqa: E402
from musik import scan as scan_mod   # noqa: E402
from musik.session import Decider, NetworkErrorRecorder  # noqa: E402

# Fake per-file tags: {absolute path: {field: value}}
TAGS: dict[str, dict[str, str]] = {}


def fake_tag(f: str, field: str) -> str:
    return TAGS.get(os.path.normcase(f), {}).get(field, "")


asis_mod._tag = fake_tag
scan_mod.tag_of = fake_tag


def make_unit(name: str, files: list[tuple[str, dict[str, str]]],
              guessed: dict, singleton: bool = False) -> dict:
    d = os.path.join(tmp, name)
    os.makedirs(d, exist_ok=True)
    paths = []
    for fname, tags in files:
        p = os.path.join(d, fname)
        open(p, "wb").close()
        TAGS[os.path.normcase(p)] = tags
        paths.append(p)
    return {
        "path": d, "files": paths, "n_files": len(paths),
        "singleton": singleton, "guessed": guessed,
    }


def decide(unit: dict) -> dict | None:
    d = Decider(NetworkErrorRecorder(), auto_accept_distance=0.25, unit=unit)
    return d._tier3_check()


# 1) normal album, folder guess agrees with the tags -> asis
u = make_unit("scene-release", [
    ("01.mp3", {"albumartist": "Anas", "artist": "Anas",
                "album": "FUENGIROLA", "title": "Fuengirola"}),
], {"artist": "Anas", "album": "FUENGIROLA"})
r = decide(u)
assert r is not None and r["status"] == "asis", r
assert "folder and tags agree" in r["reason"], r
print("1) scene album, folder+tags agree -> asis OK")

# 2) normal album, folder parse contradicts the tags -> no tier 3
#    (names must differ clearly: beets string_dist is letter-level, so
#    "Artist A" vs "Artist B" would still count as minor spelling noise)
u = make_unit("wrong-folder", [
    ("01.mp3", {"albumartist": "Nine Inch Nails", "artist": "Nine Inch Nails",
                "album": "Pretty Hate Machine", "title": "Head Like a Hole"}),
], {"artist": "Abba", "album": "Waterloo"})
assert decide(u) is None
print("2) folder/tags disagree -> stays review OK")

# 3) fetch staging: folder name is job metadata (guessed is garbage),
#    per-track album tags differ (playlist spans releases) -> asis NOW
u = make_unit("fetch-20260921-190500-spotify-playlist-bestof", [
    ("a.m4a", {"artist": "Lebanon Hanover", "album": "Besides the Abyss",
               "title": "Gallowdance"}),
    ("b.m4a", {"artist": "Lebanon Hanover", "album": "Spiral Girls",
               "title": "Sadness Is Rebellion"}),
], {"artist": "", "album": "bestof"})
r = decide(u)
assert r is not None and r["status"] == "asis", r
assert "fetch staging" in r["reason"], r
print("3) fetch playlist unit -> asis at import time OK (EPIC 4.2)")

# 4) fetch staging, but one track lacks artist/title -> no tier 3
u = make_unit("fetch-20260921-191000-youtube-playlist-gaps", [
    ("a.m4a", {"artist": "X", "album": "Y", "title": "Z"}),
    ("b.m4a", {"artist": "", "album": "", "title": ""}),
], {"artist": "", "album": "gaps"})
assert decide(u) is None
print("4) fetch unit with incomplete tags -> stays out of tier 3 OK")

# 5) singleton with per-track albums, complete artist/title -> asis
u = make_unit("chart-dump", [
    ("01.mp3", {"artist": "A One", "album": "Single A", "title": "T1"}),
    ("02.mp3", {"artist": "B Two", "album": "Single B", "title": "T2"}),
], {"artist": "", "album": ""}, singleton=True)
r = decide(u)
assert r is not None and r["status"] == "asis", r
print("5) singleton unit, tags complete -> asis OK")

print("smoke_tier3: all assertions passed")
