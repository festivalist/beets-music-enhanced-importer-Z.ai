# -*- coding: utf-8 -*-
"""Smoke test for musik/plex.py upload_playlist with mocked HTTP.

Run:  python manual_tests/smoke_plex_upload.py
No Plex server needed: requests is monkeypatched; state is isolated.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp()
m3u = os.path.join(tmp, "Best of 2026.m3u")
with open(m3u, "w", encoding="utf-8") as f:
    f.write("#EXTM3U\nC:\\Music\\x.m4a\n")

from musik import plex as PX  # noqa: E402

CFG = {"url": "http://plex:32400", "token": "T", "section": "Musik",
       "playlists": True, "playlist_attempts": 3, "playlist_wait": 0}

PX.plex_config = lambda: dict(CFG)
PX._resolve_section = lambda cfg: ("7", "Musik")

calls = {"post": 0, "get": 0, "put": []}


class FakeResp:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


PLAYLISTS_EMPTY = (
    '<Playlist ratingKey="42" guid="file://C:/playlists/Best%20of%202026.m3u"'
    ' title="Best of 2026" leafCount="0"/>'
)
PLAYLISTS_FILLED = (
    '<Playlist ratingKey="42" guid="com.plexapp.plugins.library:'
    + m3u.replace("\\", "/") + '" title="Best of 2026" leafCount="97"/>'
)


def fake_post(url, **kw):
    calls["post"] += 1
    return FakeResp(200)


def fake_get(url, **kw):
    calls["get"] += 1
    # first poll: playlist there but tracks not scanned yet -> retry
    if calls["get"] == 1:
        return FakeResp(200, "<MediaContainer>" + PLAYLISTS_EMPTY + "</MediaContainer>")
    return FakeResp(200, "<MediaContainer>" + PLAYLISTS_FILLED + "</MediaContainer>")


def fake_put(url, **kw):
    calls["put"].append((url, kw.get("params")))
    return FakeResp(200)


PX.requests.post = fake_post
PX.requests.get = fake_get
PX.requests.put = fake_put

ok, note = PX.upload_playlist(m3u, title="Best of 2026 – Sommer")
print("result:", ok, "|", note)
assert ok, note
assert calls["post"] == 2, calls          # retried once while leafCount=0
assert calls["put"] and calls["put"][0][1]["title"] == "Best of 2026 – Sommer"
assert "97 Track(s)" in note

# error path: server rejects the upload
PX.requests.post = lambda url, **kw: FakeResp(404, "nope")
ok2, note2 = PX.upload_playlist(m3u, title="X")
print("result2:", ok2, "|", note2)
assert not ok2 and "HTTP 404" in note2

# disabled via config
PX.plex_config = lambda: dict(CFG, playlists=False)
ok3, note3 = PX.upload_playlist(m3u)
assert not ok3 and note3 == ""
print("ALL PLEX SMOKE TESTS PASSED")
