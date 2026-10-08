# -*- coding: utf-8 -*-
"""Smoke test for the MusicGrabber HTTP client and bot routing (EPIC 2.4).

Run:  python manual_tests/smoke_musicgrabber.py
Pure logic — requests is monkeypatched; fixtures mirror the REAL API
shapes probed against the live instance on 2026-10-08 (including the
observed ranking quirk: a cover/party mix ranked above the official
video).
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from musik import musicgrabber as MG  # noqa: E402


class Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


CALLS: list[dict] = []


def route(method, url, json=None, timeout=None):
    CALLS.append({"method": method, "url": url, "json": json})
    if url.endswith("/api/settings"):
        return Resp(200, {"settings": {}})
    if url.endswith("/api/search"):
        return Resp(200, {
            "results": [
                {"video_id": "js_hwoEqKC6", "title": "Chelsea Dagger",
                 "artist": None, "channel": "The Professional DJ",
                 "duration": "5:15", "is_playlist": False, "video_count": None,
                 "source": "jiosaavn", "quality": "AAC 320kbps",
                 "relevance_score": 220, "quality_tier": 4},
                {"video_id": "sEXHeTcxQy4",
                 "title": "The Fratellis - Chelsea Dagger",
                 "artist": None, "channel": "The Fratellis",
                 "duration": "3:50", "is_playlist": False, "video_count": 30,
                 "source": "youtube", "quality": None,
                 "relevance_score": 150, "quality_tier": 0},
            ],
            "search_token": "tok-123",
        })
    if url.endswith("/api/download"):
        return Resp(200, {"id": 77})
    if "/api/jobs/77" in url:
        return Resp(200, {"id": 77, "status": "completed",
                          "title": "The Fratellis - Chelsea Dagger",
                          "progress_stage": None})
    return Resp(404, None, "nope")


MG.requests.request = route

# 1) available
assert MG.available() is True
MG.requests.request = lambda *a, **kw: (_ for _ in ()).throw(
    MG.requests.ConnectionError("down"))
assert MG.available() is False
MG.requests.request = route
print("1) available() ok/boom OK")

# 2) search normalization (duration parsed, artist falls back to channel)
token, results = MG.search("The Fratellis - Chelsea Dagger")
assert token == "tok-123" and len(results) == 2
r0, r1 = results
assert r0["artist"] == "The Professional DJ" and r0["duration_secs"] == 315
assert r1["artist"] == "The Fratellis" and r1["duration_secs"] == 230
assert r1["relevance"] == 150 and r0["quality_tier"] == 4
print("2) search normalization OK")

# 3) pick_result: the cover/party mix must NOT win when the query names
#    the artist (real-world case observed 2026-10-08)
pick = MG.pick_result("The Fratellis - Chelsea Dagger", results)
assert pick["video_id"] == "sEXHeTcxQy4", pick
# bare title (no artist info): MG's own ranking decides
pick = MG.pick_result("Chelsea Dagger", results)
assert pick["video_id"] == "js_hwoEqKC6"
# playlists are never picked
pl = dict(results[1], is_playlist=True)
assert MG.pick_result("x", [pl]) is None
print("3) pick_result (cover vs original, bare title, playlists) OK")

# 4) download body carries the completeness-check pair
MG.download(pick if pick["video_id"] == "sEXHeTcxQy4" else results[1], token)
body = CALLS[-1]["json"]
assert body["download_type"] == "single" and body["source"] == "youtube"
assert body["search_token"] == "tok-123"
assert body["selected_duration_secs"] == 230
print("4) download body (token + duration) OK")

# 5) wait_for_job: completed / failed / timeout
job = MG.wait_for_job(77, timeout=10)
assert job["status"] == "completed"
print("5a) wait_for_job completed OK")


def fail_route(method, url, json=None, timeout=None):
    return Resp(200, {"id": 78, "status": "failed",
                      "error": "Duration mismatch: got 99s"})


MG.requests.request = fail_route
try:
    MG.wait_for_job(78, timeout=5)
    raise AssertionError("should have raised")
except MG.MGJobFailed as e:
    assert "Duration mismatch" in str(e)
print("5b) wait_for_job failed -> MGJobFailed OK")


class FakeTime(types.SimpleNamespace):
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        self.now += 400.0  # beyond any budget on the second poll
        return self.now

    def sleep(self, _s):
        pass


MG.time = FakeTime()
MG.requests.request = lambda *a, **kw: Resp(200, {"id": 79, "status": "running"})
try:
    MG.wait_for_job(79, timeout=10)
    raise AssertionError("should have raised")
except MG.MGJobFailed as e:
    assert "not finished" in str(e)
print("5c) wait_for_job timeout -> MGJobFailed OK")

# 6) bot routing predicate: links stay on the old chain, free text goes MG
import musik.bot as B  # noqa: E402

assert B._is_free_text("The Fratellis - Chelsea Dagger") is True
assert B._is_free_text("irgend ein lied") is True
assert B._is_free_text("https://open.spotify.com/track/abc") is False
assert B._is_free_text("https://youtu.be/abc?si=x") is False
assert B._is_free_text("https://www.youtube.com/watch?v=a&list=b") is False
print("6) bot routing predicate OK")

print("smoke_musicgrabber: all assertions passed")
