# -*- coding: utf-8 -*-
"""Smoke test for the classifier matrix (musik/scan.py, Story 6.6).

Run:  python manual_tests/smoke_scan.py
Pure logic: tag readers are monkeypatched, "files" are empty dummies —
no beets library, no network, temp-isolated.

Walks classify()'s decision space end to end:
album / multidisc collapse / nested bonus dirs / loose singletons /
playlist units (incl. own-dir packaging + missing entries) / chart-dump
split / VA compilation kept whole / scene-name parse / hidden dirs
(Story 10.1) / junk counting / corrupt-file exclusion.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp()

from musik import scan as scan_mod   # noqa: E402

# Fake per-file tags: {absolute path: {field: value}}
TAGS: dict[str, dict[str, str]] = {}
CORRUPT: set[str] = set()


def fake_tag(f: str, field: str) -> str:
    return TAGS.get(os.path.normcase(f), {}).get(field, "")


scan_mod.tag_of = fake_tag
scan_mod.readable_file = lambda p: os.path.isfile(p) and \
    os.path.normcase(p) not in CORRUPT


def build(rel: str, files: list[tuple[str, dict[str, str]]] = (),
          subdirs: dict[str, list[tuple[str, dict[str, str]]]] | None = None,
          side_files: list[str] = ()) -> str:
    """Create <tmp>/<rel>/ with dummy files; returns the ABSOLUTE dir."""
    d = os.path.join(tmp, *rel.split("/"))
    os.makedirs(d, exist_ok=True)

    def put(dirpath: str, fname: str, tags: dict[str, str]) -> None:
        p = os.path.join(dirpath, fname)
        open(p, "wb").close()
        TAGS[os.path.normcase(p)] = tags

    for fname, tags in files:
        put(d, fname, tags)
    for name, sd_files in (subdirs or {}).items():
        sd = os.path.join(d, name)
        os.makedirs(sd, exist_ok=True)
        for fname, tags in sd_files:
            put(sd, fname, tags)
    for name in side_files:
        open(os.path.join(d, name), "wb").close()
    return d


def classify(root: str):
    units, notes = scan_mod.classify(root)
    return units, notes


def by_path(units: list[dict], d: str) -> dict | None:
    for u in units:
        if os.path.normcase(u["path"]) == os.path.normcase(d):
            return u
    return None


# 1) plain album directory -> one album unit, pending
d = build("plain/Artist - Album",
          [("01.mp3", {"artist": "A", "album": "X", "title": "t1"}),
           ("02.mp3", {"artist": "A", "album": "X", "title": "t2"}),
           ("03.mp3", {"artist": "A", "album": "X", "title": "t3"}),
           ("04.mp3", {"artist": "A", "album": "X", "title": "t4"})])
units, notes = classify(os.path.join(tmp, "plain"))
u = by_path(units, d)
assert u and u["kind"] == "album" and u["status"] == "pending", u
assert not u["split_into_singletons"], u
print("1) plain album -> one pending album unit OK")

# 2) multi-disc collapse: CD1/CD2 subdirs under one parent -> ONE unit
d = build("mdisc/Artist - Album",
          subdirs={
              "CD1": [("01.mp3", {}), ("02.mp3", {})],
              "CD2": [("01.mp3", {}), ("02.mp3", {})],
          })
units, _ = classify(os.path.join(tmp, "mdisc"))
u = by_path(units, d)
assert u and u["kind"] == "multidisc" and u["n_files"] == 4, u
assert len(units) == 1, [x["path"] for x in units]
print("2) CD1/CD2 -> one collapsed multidisc unit OK")

# 3) nested audio dir INSIDE an album dir gets its own unit (bonus disc)
d = build("nested/Artist - Album",
          [("01.mp3", {}), ("02.mp3", {})])
bonus = os.path.join(d, "Bonus")
os.makedirs(bonus, exist_ok=True)
open(os.path.join(bonus, "b1.mp3"), "wb").close()
units, _ = classify(os.path.join(tmp, "nested"))
assert by_path(units, d) and by_path(units, bonus), \
    [x["path"] for x in units]
print("3) nested bonus dir -> own unit OK")

# 4) a single audio file in a directory is a ONE-TRACK ALBUM unit
#    (classify never emits the vestigial 'loose' kind; singleton-ness
#    comes later via split_into_singletons / fetch prepare)
loose_root = os.path.join(tmp, "loose")
os.makedirs(loose_root, exist_ok=True)
p = os.path.join(loose_root, "Artist - Title.mp3")
open(p, "wb").close()
units, _ = classify(loose_root)
assert len(units) == 1 and units[0]["kind"] == "album" \
    and units[0]["n_files"] == 1, units
print("4) single file -> one-track album unit OK")

# 5) playlist referencing files in ANOTHER dir -> playlist unit;
#    playlist next to its own targets -> release packaging, ignored
pl_root = os.path.join(tmp, "pl")
src_dir = os.path.join(pl_root, "mixtape")
tgt_dir = os.path.join(pl_root, "elsewhere")
os.makedirs(src_dir, exist_ok=True)
os.makedirs(tgt_dir, exist_ok=True)
t1 = os.path.join(tgt_dir, "track1.mp3")
open(t1, "wb").close()
m3u = os.path.join(src_dir, "mix.m3u")
with open(m3u, "w", encoding="utf-8") as fh:
    fh.write("../elsewhere/track1.mp3\n#EXTM3U\nmissing_file.mp3\n")
units, notes = classify(pl_root)
pls = [u for u in units if u["kind"] == "playlist"]
assert len(pls) == 1 and pls[0]["files"] == [os.path.normpath(t1)], units
assert any("missing" in n for n in notes), notes
# own-dir packaging: scene .m3u next to its tracks must NOT split them out
own_root = os.path.join(tmp, "plown")
own = build("plown/Artist - Album",
            [("01.mp3", {}), ("02.mp3", {})],
            side_files=["release.m3u"])
with open(os.path.join(own, "release.m3u"), "w", encoding="utf-8") as fh:
    fh.write("01.mp3\n02.mp3\n")
units, _ = classify(os.path.join(tmp, "plown"))
assert not [u for u in units if u["kind"] == "playlist"], units
print("5) playlist elsewhere=unit, own-dir=packaging, missing noted OK")

# 6) chart dump: many distinct artists, no shared album -> split hint
d = build("dump/Chart Dump",
          [("01.mp3", {"artist": "A One", "album": "S1", "title": "t"}),
           ("02.mp3", {"artist": "B Two", "album": "S2", "title": "t"}),
           ("03.mp3", {"artist": "C Three", "album": "S3", "title": "t"}),
           ("04.mp3", {"artist": "D Four", "album": "S4", "title": "t"})])
units, _ = classify(os.path.join(tmp, "dump"))
u = by_path(units, d)
assert u and u["split_into_singletons"] \
    and "multi-artist-dir" in u["hints"], u
print("6) chart dump -> split_into_singletons OK")

# 7) VA compilation: distinct artists but ONE shared album tag -> whole
d = build("va/VA - Compilation",
          [("01.mp3", {"artist": "A One", "album": "Comp", "title": "t"}),
           ("02.mp3", {"artist": "B Two", "album": "Comp", "title": "t"}),
           ("03.mp3", {"artist": "C Three", "album": "Comp", "title": "t"}),
           ("04.mp3", {"artist": "D Four", "album": "Comp", "title": "t"})])
units, _ = classify(os.path.join(tmp, "va"))
u = by_path(units, d)
assert u and not u["split_into_singletons"], u
print("7) consistent album tag keeps the VA compilation whole OK")

# 8) scene-name parse: underscores + media tail. Album/year come out
#    clean; the artist keeps the dump-site prefix ('2HOT2PLAY') — the
#    folder-agreement tolerance absorbs that noise downstream.
d = build("scene/2HOT2PLAY__Armin_Hermann_-_Arriba-(TIPSY083)-SINGLE-WEB-2026-iDC",
          [("01.mp3", {}), ("02.mp3", {})])
units, _ = classify(os.path.join(tmp, "scene"))
u = by_path(units, d)
assert "Armin Hermann" in u["guessed"]["artist"], u["guessed"]
assert u["guessed"]["album"] == "Arriba", u["guessed"]
assert u["year_guess"] == 2026, u["guessed"]
print("8) scene folder parse (album/year clean, artist w/ prefix) OK")

# 9) hidden dirs are invisible (Story 10.1): .mg_staging yields nothing
hid_root = os.path.join(tmp, "hidden")
hid = os.path.join(hid_root, ".mg_staging", "job-1")
os.makedirs(hid, exist_ok=True)
open(os.path.join(hid, "01.mp3"), "wb").close()
units, _ = classify(hid_root)
assert not units, units
print("9) hidden dirs invisible to the ingest OK (Story 10.1)")

# 10) junk files counted; desktop.ini/thumbs.db exempt
d = build("junk/Artist - Album",
          [("01.mp3", {}), ("02.mp3", {})],
          side_files=["cover.jpg", "release.nfo", "desktop.ini"])
units, _ = classify(os.path.join(tmp, "junk"))
jf = scan_mod.junk_files()
assert any(f.endswith("cover.jpg") for f in jf), jf
assert any(f.endswith("release.nfo") for f in jf), jf
assert not any(f.endswith("desktop.ini") for f in jf), jf
print("10) junk files counted, OS noise exempt OK")

# 11) corrupt files never enter the unit; unit records them
d = build("corrupt/Artist - Album",
          [("01.mp3", {}), ("02.mp3", {})])
CORRUPT.add(os.path.normcase(os.path.join(d, "02.mp3")))
units, _ = classify(os.path.join(tmp, "corrupt"))
u = by_path(units, d)
assert u["files"] == [os.path.normpath(os.path.join(d, "01.mp3"))], u
assert u["unreadable_files"], u
print("11) corrupt file excluded from unit, recorded OK")

# 12) empty directory tree -> no units at all
empty_root = os.path.join(tmp, "empty")
os.makedirs(empty_root, exist_ok=True)
units, _ = classify(empty_root)
assert not units, units
print("12) empty root -> no units OK")

print("smoke_scan: alle Assertionen grün")
