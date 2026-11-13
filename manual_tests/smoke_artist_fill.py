# -*- coding: utf-8 -*-
"""Smoke test for the artist-fill repair on asis imports (Story 11.5).

Run:  python manual_tests/smoke_artist_fill.py
Streaming-catalog sources (live case 2026-11-13: jiosaavn) can write a
valid ALBUMARTIST while the per-track ARTIST tag is junk ("Unknown").
tags_complete's identity check (`albumartist OR artist`, asis.py) then
passes and the junk artist lands in the DB. For NON-VA units the
albumartist is the identity: the asis import now fills artist := AA.
VA-like units stay out (their per-track artists are legitimately
messy — Story 10.6 owns that path).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from musik import asis as A  # noqa: E402
from musik import scan as S  # noqa: E402

WIN = os.name == "nt"


def unit(files_tags: list[dict], hints: list[str] | None = None,
         seen: list[str] | None = None) -> dict:
    return {"path": "/stg/unit", "files": [t["path"] for t in files_tags],
            "hints": hints or [], "artists_seen": seen or [],
            "singleton": True, "split_into_singletons": False}


def tag_of_monkey(files_tags: dict[str, dict]):
    """Patch scan.tag_of (asis imports it per-call) to serve fabricated tags."""
    orig = S.tag_of

    def fake(path: str, field: str) -> str:
        entry = files_tags.get(path) or {}
        return entry.get(field, "")
    S.tag_of = fake  # type: ignore
    return orig


class FakeItem:
    def __init__(self, path: str, artist: str = "", albumartist: str = ""):
        self.path = os.fsencode(path) if isinstance(path, str) else path
        self.artist = artist
        self.albumartist = albumartist


class FakeTask:
    def __init__(self, items: list[FakeItem]):
        self._items = items

    def imported_items(self):
        return self._items


def case1_fill_fires_on_live_shape():
    p = "/stg/unit/Chaise Longue.m4a"
    tags = {p: {"artist": "Unknown", "albumartist": "Wet Leg",
                "title": "Chaise Longue"}}
    orig = tag_of_monkey(tags)
    try:
        plan = A.plan_artist_fill(unit([{"path": p}]))
    finally:
        A.tag_of = orig
    assert plan == {"fill": {p: "Wet Leg"}}, plan
    task = FakeTask([FakeItem(p, artist="Unknown", albumartist="Wet Leg")])
    n = A.apply_artist_fill(task, plan)
    assert n == 1
    assert task.imported_items()[0].artist == "Wet Leg"
    print("1) live case: AA valid + artist junk -> fill fires OK")


def case2_valid_artist_untouched():
    p = "/stg/unit/t.m4a"
    tags = {p: {"artist": "Wet Leg", "albumartist": "Wet Leg",
                "title": "t"}}
    orig = tag_of_monkey(tags)
    try:
        plan = A.plan_artist_fill(unit([{"path": p}]))
    finally:
        A.tag_of = orig
    assert plan is None, plan
    print("2) valid artist: no fill, plan None OK")


def case3_aa_junk_too_no_fill():
    p = "/stg/unit/t.m4a"
    tags = {p: {"artist": "Unknown", "albumartist": "", "title": "t"}}
    orig = tag_of_monkey(tags)
    try:
        plan = A.plan_artist_fill(unit([{"path": p}]))
    finally:
        A.tag_of = orig
    assert plan is None, plan  # tags_complete refuses -> review (10.3)
    print("3) both junk: no fill (review path, 10.3) OK")


def case4_va_unit_exempt():
    p1, p2, p3 = "/stg/u/1.mp3", "/stg/u/2.mp3", "/stg/u/3.mp3"
    tags = {
        p1: {"artist": "A One", "albumartist": "Various Artists"},
        p2: {"artist": "B Two", "albumartist": "Various Artists"},
        p3: {"artist": "Unknown", "albumartist": "Various Artists"},
    }
    orig = tag_of_monkey(tags)
    try:
        plan = A.plan_artist_fill(
            unit([{"path": p1}, {"path": p2}, {"path": p3}],
                 seen=["a one", "b two", "c three"]))
    finally:
        A.tag_of = orig
    assert plan is None, "VA units are Story-10.6 territory"
    print("4) VA unit (Various Artists): exempt OK")


def case5_va_series_aa_exempt():
    p1, p2, p3 = "/stg/u/1.mp3", "/stg/u/2.mp3", "/stg/u/3.mp3"
    tags = {
        p1: {"artist": "A One", "albumartist": "Essential Albums"},
        p2: {"artist": "B Two", "albumartist": "Essential Albums"},
        p3: {"artist": "Unknown", "albumartist": "Essential Albums"},
    }
    orig = tag_of_monkey(tags)
    try:
        u = unit([{"path": p1}, {"path": p2}, {"path": p3}],
                 seen=["a one", "b two", "c three"])
        assert A.va_like_unit(u), "series-AA compilation is va_like"
        plan = A.plan_artist_fill(u)
    finally:
        A.tag_of = orig
    assert plan is None, plan
    print("5) VA series-AA compilation: exempt OK")


def case6_session_delegates():
    from musik.session import Decider, NetworkErrorRecorder

    d = Decider(NetworkErrorRecorder(), auto_accept_distance=0.25,
                unit={"hints": ["va-album"], "files": [],
                      "artists_seen": []}, lib=None)
    assert d._va_like() is True
    d2 = Decider(NetworkErrorRecorder(), auto_accept_distance=0.25,
                 unit={"hints": [], "files": [], "artists_seen": []},
                 lib=None)
    assert d2._va_like() is False
    print("6) session._va_like delegates to va_like_unit OK")


if __name__ == "__main__":
    case1_fill_fires_on_live_shape()
    case2_valid_artist_untouched()
    case3_aa_junk_too_no_fill()
    case4_va_unit_exempt()
    case5_va_series_aa_exempt()
    case6_session_delegates()
    print("smoke_artist_fill: alle Assertionen grün")
