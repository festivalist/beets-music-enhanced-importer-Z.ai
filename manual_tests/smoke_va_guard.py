# -*- coding: utf-8 -*-
"""Smoke test for the VA compilation guard + survivor import
(musik/session.py Stories 10.5/10.6).

Run:  python manual_tests/smoke_va_guard.py
Pure logic: tag readers are monkeypatched, candidates/tasks are fakes,
"files" are empty dummies with realistic names — no beets lookups, no
network, temp-isolated.

Live background (2026-10-21, windows drop): VA comps with junk folder
names ("2014 - Essential Albums - …" → guessed artist "Essential Albums")
parked in review. Their per-track tags are GOOD (even where the FILENAME
carries the typo). The guard archives compilations that are largely
already in the library; mostly-unique ones import as clean
Various-Artists albums instead of parking in review.
"""

import os
import sys
import tempfile
import types

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


class FakeItem:
    def __init__(self, artist, title):
        self.artist = artist
        self.title = title


class FakeLib:
    def __init__(self, pairs):
        self._items = [FakeItem(a, t) for a, t in pairs]

    def items(self):
        return list(self._items)


class FakeDist(dict):
    def __float__(self):
        return sum(self.values())


def fake_task(candidates, artist="Essential Albums",
              album="Essential 80's Black Funky"):
    return types.SimpleNamespace(
        rec=None, candidates=list(candidates), items=[],
        cur_artist=artist, cur_album=album, paths=[b"x"],
    )


def weak_candidate(artist="Various Artists", album="Essential 80's: Funky Dance"):
    info = types.SimpleNamespace(
        data_source="MusicBrainz", artist=artist, artists=[artist],
        album=album, album_id="id-1", track_id="id-1", year=2014, tracks=[],
        title=album,
    )
    return types.SimpleNamespace(
        info=info, distance=FakeDist({"album": 0.30}),
        mapping={}, extra_items=[],
    )


def make_va_unit(name, tracks, album="Essential 80's Black Funky",
                 guessed=None):
    """tracks: list of (filename, {artist,title,albumartist...})."""
    d = os.path.join(tmp, name)
    os.makedirs(d, exist_ok=True)
    paths = []
    for fname, tags in tracks:
        p = os.path.join(d, fname)
        open(p, "wb").close()
        TAGS[os.path.normcase(p)] = tags
        paths.append(p)
    return {
        "path": d, "import_path": d, "files": paths, "n_files": len(paths),
        "singleton": False, "hints": ["multi-artist-dir"],
        "guessed": guessed or {"artist": "Essential Albums", "album": album},
    }


def essential_tracks(n=10, album="Essential 80's Black Funky", aa=""):
    """windows-drop style: filename is 'Title - Artist', tags are correct."""
    out = []
    for i in range(1, n + 1):
        title, artist = f"Track {i:02d}", f"Artist {i:02d}"
        out.append((
            f"{i:02d}. {title} - {artist}.mp3",
            {"artist": artist, "title": title, "album": album,
             "albumartist": aa},
        ))
    return out


netrec = NetworkErrorRecorder()

# 1) parse_track_filename: track-number prefixes and both orientations
assert scan_mod.parse_track_filename(
    "01. Inside Out - Odyssey.mp3") == ("Inside Out", "Odyssey")
assert scan_mod.parse_track_filename(
    "12 - Some Artist - Some Title.flac") == ("Some Artist", "Some Title")
assert scan_mod.parse_track_filename("no separator here.mp3") is None
assert scan_mod.parse_track_filename("07. Only One Part.mp3") is None
print("1) parse_track_filename conventions OK")

# 2) plan_va_normalize: tags authoritative, filename fills gaps under the
#    unit's majority-voted orientation (title-first like the windows drop)
tracks = essential_tracks(3)
u = make_va_unit("plan-va", tracks)
# a 4th file with an empty artist tag; filename orientation is title-first
p4 = os.path.join(tmp, "plan-va", "04. Fill Title - Fill Artist.mp3")
open(p4, "wb").close()
TAGS[os.path.normcase(p4)] = {"artist": "", "title": "Fill Title",
                              "album": "X", "albumartist": ""}
u["files"].append(p4)
u["n_files"] = 4
plan = asis_mod.plan_va_normalize(u["files"])
assert plan is not None, plan
assert plan["aa"] is True, plan
assert plan["fill"].get(os.fsdecode(p4)) == ("Fill Artist", ""), plan
print("2) plan_va_normalize: tags win, filename fills, orientation voted OK")

# 3) plan_va_normalize refuses when a file is unresolvable
p5 = os.path.join(tmp, "plan-va", "09 NoHelp AtAll.mp3")
open(p5, "wb").close()
TAGS[os.path.normcase(p5)] = {"artist": "", "title": "", "album": "X",
                              "albumartist": ""}
u["files"].append(p5)
assert asis_mod.plan_va_normalize(u["files"]) is None
print("3) plan_va_normalize: unresolvable file -> stays review OK")

# 4) guard end-to-end through decide_album: 8/10 tracks in the library
#    -> ignored (never reaches tier 3 or review)
lib_pairs = [(f"Artist {i:02d}", f"Track {i:02d}") for i in range(1, 9)]
u = make_va_unit("guard-redundant", essential_tracks(10))
dec = Decider(netrec, auto_accept_distance=0.25, unit=u, lib=FakeLib(lib_pairs))
action, record = dec.decide_album(fake_task([weak_candidate()]))
assert action == "skip" and record["status"] == "ignored", (action, record)
assert "redundant" in record["reason"] and "8/10" in record["reason"], record
print("4) VA guard: 8/10 in library -> ignored OK (Story 10.5)")

# 5) survivor end-to-end: 0/10 in library, junk folder vetoed tier 3
#    -> apply-asis with normalize_va (Various Artists)
u = make_va_unit("guard-survivor", essential_tracks(10))
dec = Decider(netrec, auto_accept_distance=0.25, unit=u, lib=FakeLib([]))
action, record = dec.decide_album(fake_task([weak_candidate()]))
assert action == "apply-asis" and record["status"] == "asis", (action, record)
assert record["normalize_va"]["aa"] is True, record
assert "Various Artists" in record["reason"], record
print("5) VA survivor: unique comp -> normalized as-is OK (Story 10.6)")

# 6) without a library handle (dry run) the guard abstains -> review
u = make_va_unit("guard-dry", essential_tracks(10))
dec = Decider(netrec, auto_accept_distance=0.25, unit=u)
action, record = dec.decide_album(fake_task([weak_candidate()]))
assert action == "skip" and record["status"] == "review", (action, record)
print("6) dry run without lib: guard abstains -> review OK")

# 7) below min_tracks the guard abstains (3 tagged files < 5)
u = make_va_unit("guard-tiny", essential_tracks(3))
dec = Decider(netrec, auto_accept_distance=0.25, unit=u,
              lib=FakeLib([(f"Artist {i:02d}", f"Track {i:02d}")
                           for i in range(1, 4)]))
action, record = dec.decide_album(fake_task([weak_candidate()]))
assert action == "skip" and record["status"] == "review", (action, record)
print("7) below va_redundant_min_tracks: guard abstains OK")

# 8) apply_va_plan mutates the in-memory items (beets writes them later)
item = types.SimpleNamespace(
    path=os.fsencode(p4), artist="", title="Fill Title", albumartist="")
task = types.SimpleNamespace(imported_items=lambda: [item])
n = asis_mod.apply_va_plan(
    task, {"fill": {os.fsdecode(p4): ("Fill Artist", "")}, "aa": True})
assert n == 2, n
assert item.artist == "Fill Artist" and item.albumartist == "Various Artists"
print("8) apply_va_plan: filename fill + AA normalization OK")

# 9) va_gate_unit (asis-fallback gate): redundant -> ignored, unique ->
#    normalize (empty dummy files: mutagen skips writes, gate still fires)
u = make_va_unit("gate-unit-redundant", essential_tracks(10))
gate, note = asis_mod.va_gate_unit(u, FakeLib(lib_pairs))
assert gate == "ignored" and "redundant" in note, (gate, note)
u = make_va_unit("gate-unit-unique", essential_tracks(10))
gate, note = asis_mod.va_gate_unit(u, FakeLib([]))
assert gate == "normalize" and "0/10" in note, (gate, note)
# not va_like (no hints, no distinct artists) -> pass
u2 = make_va_unit("gate-unit-single", [
    ("01.mp3", {"artist": "One Band", "title": "T1", "album": "A",
                "albumartist": "One Band"}),
], guessed={"artist": "One Band", "album": "A"})
u2["hints"] = []
gate, _note = asis_mod.va_gate_unit(u2, FakeLib([]))
assert gate == "pass", gate
print("9) va_gate_unit: ignored/normalize/pass OK (asis fallback)")

# 10) thin tags + parseable filenames: overlap is measured on the
#     RESOLVED identity (tags + filename fills) — a unique comp imports,
#     a redundant one is ignored, both without review
thin = []
for i in range(1, 7):
    p = os.path.join(tmp, f"thin-{i}", f"{i:02d}. Thin Artist {i} - Thin Title {i}.mp3")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").close()
    tags = {"artist": "", "title": "", "album": "Thin Comp", "albumartist": ""}
    if i == 1:  # one tagged reference file votes the orientation
        tags = {"artist": "Thin Artist 1", "title": "Thin Title 1",
                "album": "Thin Comp", "albumartist": ""}
    TAGS[os.path.normcase(p)] = tags
    thin.append(p)
u = make_va_unit("thin-unique", [
    (os.path.basename(p), {}) for p in thin
])
u["files"] = list(thin)
u["n_files"] = len(thin)
dec = Decider(netrec, auto_accept_distance=0.25, unit=u, lib=FakeLib([]))
action, record = dec.decide_album(fake_task([weak_candidate()]))
assert action == "apply-asis" and record["status"] == "asis", (action, record)
assert record["normalize_va"]["fill"], record
lib_pairs_thin = [("Thin Artist %d" % i, "Thin Title %d" % i) for i in range(1, 6)]
u = make_va_unit("thin-redundant", [(os.path.basename(p), {}) for p in thin])
u["files"] = list(thin)
dec = Decider(netrec, auto_accept_distance=0.25, unit=u, lib=FakeLib(lib_pairs_thin))
action, record = dec.decide_album(fake_task([weak_candidate()]))
assert action == "skip" and record["status"] == "ignored", (action, record)
assert "5/6" in record["reason"], record
print("10) thin tags: resolved-identity overlap -> survivor / ignored OK")

# 11) junk release credit ("Essential Albums" on a 6-artist comp): the
#     unit counts as va_like, the VA block wins BEFORE tier 3 (whose
#     folder check would be fooled by folder+tags agreeing on the junk)
#     and the plan replaces the junk credit with Various Artists
tracks11 = essential_tracks(6)
u = make_va_unit("junk-aa", tracks11)
for p in u["files"]:
    TAGS[os.path.normcase(p)]["albumartist"] = "Essential Albums"
u["artists_seen"] = [f"artist {i:02d}" for i in range(1, 7)]
u["hints"] = []
dec = Decider(netrec, auto_accept_distance=0.25, unit=u, lib=FakeLib([]))
assert dec._va_like() is True
action, record = dec.decide_album(fake_task([weak_candidate()]))
assert action == "apply-asis" and record["status"] == "asis", (action, record)
assert record["normalize_va"]["aa_overwrite"] is True, record
item = types.SimpleNamespace(
    path=os.fsencode(u["files"][0]), artist="Artist 01",
    title="Track 01", albumartist="Essential Albums")
task = types.SimpleNamespace(imported_items=lambda: [item])
asis_mod.apply_va_plan(task, record["normalize_va"])
assert item.albumartist == "Various Artists", item.albumartist
print("11) junk albumartist: va_like + replaced before tier 3 OK")

print("smoke_va_guard: all assertions passed")
