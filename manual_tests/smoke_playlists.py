# -*- coding: utf-8 -*-
"""Smoke test for musik/playlists.py pure logic (no beets, no Plex).

Run:  python manual_tests/smoke_playlists.py
Isolates state_dir and the m3u dir into a temp folder.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp()
st_dir = os.path.join(tmp, "state")
os.makedirs(st_dir)
m3u_dir = os.path.join(tmp, "m3u")
os.makedirs(m3u_dir)

from musik import paths as paths_mod  # noqa: E402

_real_musik_config = paths_mod.musik_config


def fake_cfg():
    cfg = dict(_real_musik_config())
    cfg["state_dir"] = st_dir
    return cfg


paths_mod.musik_config = fake_cfg
import musik.playlists as P  # noqa: E402

# 1) is_playlist_query
tests = [
    ("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=x", True),
    ("https://open.spotify.com/album/abc123", False),
    ("https://open.spotify.com/track/xyz", False),
    ("https://music.youtube.com/playlist?list=PLxyz", True),
    ("https://www.youtube.com/watch?v=abc", False),
    ("https://youtu.be/abc", False),
    ("Rammstein - Deutschland", False),
]
for q, want in tests:
    got = P.is_playlist_query(q)
    assert got == want, (q, got, want)
print("is_playlist_query OK")

# 2) sidecar parsing (EXTINF + rel/abs paths + plain lines)
job_dir = os.path.join(tmp, "fetch-20260921-120000-spotify-BestOf")
os.makedirs(job_dir)
sc = os.path.join(job_dir, "Best of 2026.m3u8")
lines = [
    "#EXTM3U",
    "#EXTINF:214,Rammstein - Deutschland",
    "Rammstein - Deutschland.m4a",
    "#EXTINF:200,Kraftklub - Song fuer mich",
    job_dir.replace("\\", "/") + "/Kraftklub - Song fuer mich.m4a",
    "Plain - No Meta.m4a",
]
with open(sc, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
entries = P._parse_sidecar(sc)
assert entries[0] == {"file": "Rammstein - Deutschland.m4a",
                      "artist": "Rammstein", "title": "Deutschland"}, entries[0]
assert entries[1]["file"] == "Kraftklub - Song fuer mich.m4a"
assert entries[1]["title"] == "Song fuer mich"
assert entries[2]["title"] == "No Meta", entries[2]
print("sidecar parse OK", len(entries))

# 3) matching: remastered suffix + artist anchor + duplicate-title disambiguation
items = [
    {"id": 1, "path": "C:\\Music\\R\\2019 - RAMMSTEIN\\01 Deutschland.m4a",
     "title": "Deutschland", "artist": "Rammstein", "albumartist": "Rammstein"},
    {"id": 2, "path": "C:\\Music\\K\\2012 - Mit K\\04 Song fuer mich (2012 Remaster).m4a",
     "title": "Song fuer mich (2012 Remaster)", "artist": "Kraftklub",
     "albumartist": "Kraftklub"},
    {"id": 3, "path": "C:\\Music\\X\\Singles\\A - Feuer.m4a",
     "title": "Feuer", "artist": "Andreas", "albumartist": "Andreas"},
    {"id": 4, "path": "C:\\Music\\X\\Singles\\B - Feuer.m4a",
     "title": "Feuer", "artist": "Beatrice", "albumartist": "Beatrice"},
]
e1 = {"file": "Rammstein - Deutschland.m4a", "artist": "Rammstein",
      "title": "Deutschland"}
e2 = {"file": "Kraftklub - Song fuer mich.m4a", "artist": "Kraftklub",
      "title": "Song fuer mich"}
e3 = {"file": "Beatrice - Feuer.m4a", "artist": "Beatrice", "title": "Feuer"}
e4 = {"file": "Nirvana - Smells Like Teen Spirit.m4a", "artist": "Nirvana",
      "title": "Smells Like Teen Spirit"}
P._match_entries([e1, e2, e3, e4], items)
assert e1["dest"].endswith("01 Deutschland.m4a"), e1
assert "2012 Remaster" in e2["dest"], e2
assert e3["dest"].endswith("B - Feuer.m4a"), e3   # artist disambiguates
assert e4.get("dest") is None                     # not in the library
print("matching OK")

# 4) state io + m3u write via a fake job
class FakeJob:  # noqa: D401 - minimal FetchJob stand-in
    job_id = "fetch-20260921-120000-spotify-BestOf"
    job_dir = job_dir
    query = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"


P.m3u_dir = lambda: m3u_dir
spec = {"name": "Best of 2026", "entries": [dict(e1), dict(e2), dict(e4)]}
states = P.build(FakeJob(), [spec], ids_before=set())  # empty diff = all new
assert len(states) == 1
pl = states[0]
have = sum(1 for t in pl["tracks"] if t.get("dest"))
assert have == 2, pl["tracks"]
m3u = os.path.join(m3u_dir, "Best of 2026.m3u")
content = open(m3u, encoding="utf-8").read()
assert content.startswith("#EXTM3U")
assert "01 Deutschland.m4a" in content
assert "Smells" not in content
print("m3u OK ->", m3u)
print(P.summarize(pl))

# 5) rebuild after '/asis': e4's track now exists -> filled, order kept
items.append({"id": 9, "path": "C:\\Music\\S\\1991 - Nevermind\\01 Smells Like Teen Spirit.m4a",
              "title": "Smells Like Teen Spirit", "artist": "Nirvana",
              "albumartist": "Nirvana"})
P._items_since = lambda ids: items
touched = P.rebuild([job_dir])
assert len(touched) == 1, touched
assert all(t.get("dest") for t in touched[0]["tracks"]), touched[0]["tracks"]
content = open(m3u, encoding="utf-8").read()
assert "Nevermind" in content
print("rebuild OK:", P.summarize(touched[0]))

# 6) filename safety (umlauts kept, path chars dropped)
assert P._safe_filename('Best: "Hits"/2026?') == "Best Hits2026"
assert P._safe_filename("AE OE UE - Foen") == "AE OE UE - Foen"
print("filename safety OK")

# 7) yt-dlp order extraction (pure part): name match, loose match,
#    tag-title match, skipped unavailable entry, leftovers appended
info = {
    "_type": "playlist",
    "title": "Cursum Perficio (2026)",
    "entries": [
        {"title": "Persistence of Memory", "channel": "Anthrax"},
        {"title": "The Long Goodbye", "channel": "Anthrax"},   # loose match
        {"title": "Gone (Official Video)", "channel": "Anthrax"},  # tag match
        {"title": "Unavailable Song", "channel": "Anthrax"},   # no file
    ],
}
files = [
    "D:\\dl\\The Long Goodbye (Official Audio).m4a",   # loose name match
    "D:\\dl\\Persistence of Memory.m4a",               # exact name match
    "D:\\dl\\03 It's For The Kids.m4a",                # leftover
    "D:\\dl\\track4.m4a",                              # matched via tag
]
tags = {
    "track4.m4a": {"file": "track4.m4a", "artist": "Anthrax", "title": "Gone"},
}
got = P._order_from_info(info, files, tags)
assert got is not None
name, ordered = got
assert name == "Cursum Perficio (2026)"
assert [o["file"] for o in ordered] == [
    "Persistence of Memory.m4a",
    "The Long Goodbye (Official Audio).m4a",
    "track4.m4a",
    "03 It's For The Kids.m4a",          # leftover appended at the end
]
assert ordered[2]["title"] == "Gone"     # tag title preferred
print("yt-dlp order matching OK")


# 8) prepare(): youtube job uses yt-dlp order; mtime fallback otherwise
class FakeYTJob:
    job_id = "fetch-20260922-090000-youtube-Anthrax"
    job_dir = os.path.join(tmp, "fetch-20260922-090000-youtube-Anthrax")
    query = "https://www.youtube.com/playlist?list=PLxyz"
    kind = "youtube"
    files = ["f3.m4a", "f1.m4a", "f2.m4a"]


os.makedirs(FakeYTJob.job_dir, exist_ok=True)  # no sidecar inside
# real _tag_entries is safe on missing files (tag_of swallows errors)
P._youtube_order = lambda job: ("Echte Reihenfolge", [
    {"file": "f2.m4a", "artist": "A", "title": "T2"},
    {"file": "f1.m4a", "artist": "A", "title": "T1"},
])
specs = P.prepare(FakeYTJob)
assert specs and specs[0]["name"] == "Echte Reihenfolge"
assert [e["file"] for e in specs[0]["entries"]] == ["f2.m4a", "f1.m4a"]
print("prepare (yt order) OK")

# mtime fallback: older mtime first, not alphabetical
P._youtube_order = lambda job: None
real = []
for i, (nm, age) in enumerate((("b.m4a", 300), ("a.m4a", 200), ("c.m4a", 100))):
    pth = os.path.join(FakeYTJob.job_dir, nm)
    with open(pth, "w") as fh:
        fh.write("x")
    os.utime(pth, (age, age))
    real.append(pth)
FakeYTJob.files = real
specs = P.prepare(FakeYTJob)
assert [e["file"] for e in specs[0]["entries"]] == ["c.m4a", "a.m4a", "b.m4a"]
assert specs[0]["name"] == FakeYTJob.job_id.split("-", 3)[3]
print("prepare (mtime fallback) OK")
print("ALL SMOKE TESTS PASSED")
