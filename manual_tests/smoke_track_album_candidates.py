# -*- coding: utf-8 -*-
"""Smoke test for the track→album offer candidates (Story 2.5).

Run:  python manual_tests/smoke_track_album_candidates.py
Pure logic — MusicBrainz requests are monkeypatched with fixture payloads
shaped like ws/2/recording search results. Live references probed
2026-10-09: Fratellis "Mistress Mabel" → Here We Stand; Bicep "Glue" →
album + EP + soundtrack; Grauzone "Eisbaer" (ASCII spelling!) only matches
after de-transliteration.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from musik import releases as R  # noqa: E402


def rec(score, artist, title, releases):
    return {"score": score, "title": title,
            "artist-credit": [{"name": artist, "artist": {"name": artist}}],
            "releases": releases}


def rel(rg_id, title, ptype, secondary=None, date="", status="Official",
        rg_date=""):
    return {"title": title, "status": status, "date": date,
            "release-group": {"id": rg_id, "title": title,
                              "primary-type": ptype,
                              "secondary-types": secondary or [],
                              "first-release-date": rg_date}}


WANT = R._tokens("Example Band")

# 1) single album containing the track → exactly that candidate
cands = R._recording_release_groups(
    [rec(100, "Example Band", "Song",
         [rel("rg-album", "Great Album", "Album", rg_date="2001-05-01")])],
    WANT, 3)
assert len(cands) == 1 and cands[0]["rg_mbid"] == "rg-album"
assert cands[0]["type"] == "album" and cands[0]["year"] == "2001"
print("1) single album OK")

# 2) single + EP + album: singles never offered (the user has the track),
#    EP and album both are
cands = R._recording_release_groups(
    [rec(100, "Example Band", "Song", [
        rel("rg-single", "Song", "Single", rg_date="2000-01-01"),
        rel("rg-ep", "Nice EP", "EP", rg_date="2000-06-01"),
        rel("rg-album", "Great Album", "Album", rg_date="2001-05-01"),
    ])],
    WANT, 3)
assert sorted(c["rg_mbid"] for c in cands) == ["rg-album", "rg-ep"], cands
print("2) single filtered, EP+album offered OK")

# 3) compilations, live albums and soundtracks dropped; bootlegs/promos
#    dropped (live case: Bowie "Heroes" offered a 2009 movie soundtrack)
cands = R._recording_release_groups(
    [rec(100, "Example Band", "Song", [
        rel("rg-comp", "Now 43", "Album", secondary=["Compilation"],
            rg_date="2002-01-01"),
        rel("rg-live", "Live Somewhere", "Album", secondary=["Live"],
            rg_date="2003-01-01"),
        rel("rg-ost", "Film OST", "Album", secondary=["Soundtrack"],
            rg_date="2009-05-05"),
        rel("rg-boot", "Bootleg", "Album", status="Bootleg",
            rg_date="2004-01-01"),
        rel("rg-album", "Great Album", "Album", rg_date="2001-05-01"),
    ])],
    WANT, 5)
assert [c["rg_mbid"] for c in cands] == ["rg-album"]
print("3) compilation/live/soundtrack/bootleg filtered OK")

# 4) artist-token guard: covers credit the ORIGINAL artist in the title,
#    never in their own credit — their releases must not become candidates
cands = R._recording_release_groups(
    [rec(100, "Paris Music", "Song (Originally Performed By Example Band)",
         [rel("rg-cover", "Karaoke Hits", "Album", rg_date="2010-01-01")]),
     rec(80, "Example Band", "Song",
         [rel("rg-album", "Great Album", "Album", rg_date="2001-05-01")])],
    WANT, 3)
assert [c["rg_mbid"] for c in cands] == ["rg-album"]
print("4) cover-artist guard OK")

# 5) NEWEST guarantee: with more candidates than buttons the newest
#    release group displaces the weakest (user rule 2026-10-09)
recordings = [
    rec(100, "Example Band", "Song",
        [rel("rg-a", "Alpha", "Album", rg_date="2001-01-01")]),
    rec(99, "Example Band", "Song",
        [rel("rg-b", "Beta", "Album", rg_date="1995-01-01")]),
    rec(98, "Example Band", "Song",
        [rel("rg-c", "Gamma", "Album", rg_date="1999-01-01")]),
    rec(50, "Example Band", "Song",
        [rel("rg-new", "Reissue Era", "Album", rg_date="2024-06-01")]),
]
cands = R._recording_release_groups(recordings, WANT, 3)
ids = [c["rg_mbid"] for c in cands]
assert ids == ["rg-a", "rg-b", "rg-new"], ids  # gamma displaced by newest
cands_all = R._recording_release_groups(recordings, WANT, 4)
assert [c["rg_mbid"] for c in cands_all] == ["rg-a", "rg-b", "rg-c", "rg-new"]
print("5) newest-always-included OK")


# 6) track_album_candidates wiring: MB search + year backfill (batched
#    release-group lookup — the recording search barely returns dates) +
#    in_library flag from beets
class Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


QUERIES: list[dict] = []


def fake_get(url, params=None, headers=None, timeout=None):
    QUERIES.append({"url": url, "params": params})
    if "/release-group" in url:  # the backfill batch lookup
        return Resp(200, {"release-groups": [
            {"id": "rg-album", "title": "Great Album",
             "first-release-date": "2001-05-01", "primary-type": "Album",
             "secondary-types": None},
            {"id": "rg-new", "title": "Reissue Era",
             "first-release-date": "2024-06-01", "primary-type": "Album",
             "secondary-types": None},
        ]})
    payload = {"recordings": [
        rec(100, "Example Band", "Song", [
            rel("rg-album", "Great Album", "Album"),
            rel("rg-new", "Reissue Era", "Album"),
        ]),
    ]}
    return Resp(200, payload)


class FakeAlbums:
    def __init__(self, present):
        self.present = present  # {rg_mbid: bool}

    def albums(self, q):
        rg = q.split(":", 1)[1]
        # beets yields album rows for the query; None-ish when absent
        if self.present.get(rg):
            yield {"mb_releasegroupid": rg}
        return
        yield  # pragma: no cover — makes this a generator either way


R.requests.get = fake_get
R.time.sleep = lambda _s: None
lib = FakeAlbums({"rg-album": True, "rg-new": False})
cands = R.track_album_candidates("Example Band", "Song", library=lib)
assert len(cands) == 2
by_id = {c["rg_mbid"]: c for c in cands}
assert by_id["rg-album"]["in_library"] is True
assert by_id["rg-new"]["in_library"] is False
assert QUERIES[0]["params"]["query"] == (
    'artist:"Example Band" AND recording:"Song" AND status:official')
# years came from the backfill (search fixtures carry none), original first
assert cands[0]["rg_mbid"] == "rg-album" and cands[0]["year"] == "2001"
assert cands[1]["rg_mbid"] == "rg-new" and cands[1]["year"] == "2024"
assert any("rgid:rg-album OR rgid:rg-new" == q["params"]["query"]
           for q in QUERIES)
print("6) wiring + year backfill + in_library flag OK")

# 6b) backfill veto: authoritative data marks a candidate a soundtrack
#     (MB search missed it) — it must NOT survive the offer
QUERIES.clear()


def veto_get(url, params=None, headers=None, timeout=None):
    if "/release-group" in url:
        return Resp(200, {"release-groups": [
            {"id": "rg-ost", "title": "Film OST",
             "first-release-date": "2009-05-05", "primary-type": "Album",
             "secondary-types": ["Soundtrack"]},
            {"id": "rg-album", "title": "Great Album",
             "first-release-date": "2001-05-01", "primary-type": "Album",
             "secondary-types": None},
        ]})
    return Resp(200, {"recordings": [
        rec(100, "Example Band", "Song", [
            rel("rg-ost", "Film OST", "Album"),
            rel("rg-album", "Great Album", "Album"),
        ]),
    ]})


R.requests.get = veto_get
cands = R.track_album_candidates("Example Band", "Song")
assert [c["rg_mbid"] for c in cands] == ["rg-album"], cands
print("6b) backfill veto (authoritative soundtrack) OK")

# 7) de-transliteration fallback: ASCII spelling finds nothing on the
#    strict pass, the ae/oe/ue/ss variant is queried next (live case:
#    Grauzone "Eisbaer" — MB's Lucene search does not fold umlauts)
QUERIES.clear()


def umlaut_get(url, params=None, headers=None, timeout=None):
    QUERIES.append(params)
    if "/release-group" in url:  # backfill for the found RG
        return Resp(200, {"release-groups": [
            {"id": "rg-grau", "title": "Grauzone",
             "first-release-date": "1981-01-01", "primary-type": "Album",
             "secondary-types": None},
        ]})
    if "Eisbaer" in params["query"]:
        return Resp(200, {"recordings": []})
    assert "Eisbär" in params["query"]
    return Resp(200, {"recordings": [
        rec(100, "Grauzone", "Eisbär",
            [rel("rg-grau", "Grauzone", "Album", rg_date="1981-01-01")]),
    ]})


R.requests.get = umlaut_get
cands = R.track_album_candidates("Grauzone", "Eisbaer")
assert len(cands) == 1 and cands[0]["rg_mbid"] == "rg-grau"
assert cands[0]["year"] == "1981"  # backfilled via the batched rgid lookup
# recording search (ASCII) → recording search (umlaut) → rgid backfill;
# both searches carry the bootleg-suppressing status filter
assert len(QUERIES) == 3 and QUERIES[1]["query"].count("ä") == 1
assert QUERIES[1]["query"].endswith("AND status:official")
assert QUERIES[2]["query"] == "rgid:rg-grau"
print("7) de-transliteration fallback OK")

# 8) MB unreachable → [] (the offer is optional, the track job must live)
R.requests.get = lambda *a, **kw: Resp(503, {})
assert R.track_album_candidates("X", "Y") == []
print("8) MB 503 → no offer OK")

print("smoke_track_album_candidates: all assertions passed")
