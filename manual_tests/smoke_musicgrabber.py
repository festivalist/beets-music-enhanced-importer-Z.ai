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
                # live case 2: karaoke-label cover, names the original
                # artist IN THE TITLE, 320 kbps, outranks everything
                {"video_id": "paris1", "title": "Chelsea Dagger "
                 "(Originally Performed By The Fratellis) [Full Vocal "
                 "Version]", "artist": None, "channel": "Paris Music",
                 "duration": "3:48", "is_playlist": False,
                 "source": "jiosaavn", "quality": "AAC 320kbps",
                 "relevance_score": 300, "quality_tier": 4,
                 "source_url": "https://aac.saavncdn.com/x.mp4"},
                # live case 1: party-mix namesake, high quality tier
                {"video_id": "js_hwoEqKC6", "title": "Chelsea Dagger",
                 "artist": None, "channel": "The Professional DJ",
                 "duration": "5:15", "is_playlist": False,
                 "source": "jiosaavn", "quality": "AAC 320kbps",
                 "relevance_score": 220, "quality_tier": 4,
                 "source_url": "https://aac.saavncdn.com/y.mp4"},
                # the real recording (rank 3!)
                {"video_id": "sEXHeTcxQy4",
                 "title": "The Fratellis - Chelsea Dagger",
                 "artist": None, "channel": "The Fratellis",
                 "duration": "3:50", "is_playlist": False, "video_count": 30,
                 "source": "youtube", "quality": None,
                 "relevance_score": 150, "quality_tier": 0,
                 "source_url": "https://www.youtube.com/watch?v=sEXHeTcxQy4"},
            ],
            "search_token": "tok-123",
        })
    if url.endswith("/api/download"):
        return Resp(200, {"id": "816f3ba5"})  # string id (live-probed)
    if url.endswith("/api/albums/resolve-release-group"):
        # live shape, probed 2026-10-09 (Here We Stand RG)
        return Resp(200, {"artist": "The Fratellis",
                          "album_title": "Here We Stand",
                          "release_mbid": "6d566ef6-199d-47f0-9df3-64c1f6f51a38",
                          "year": "2008", "track_count": 18})
    if url.endswith("/api/albums/download"):
        return Resp(200, {"import_id": "693fde90", "track_count": 18,
                          "queued_count": 18, "existing_count": 0,
                          "missing_count": 18,
                          "album_dir": "/music/Albums/The Fratellis/Here We Stand"})
    if "/api/bulk-import/" in url and url.endswith("/status"):
        # live shape, probed 2026-10-09: 14/18 done, 4 failed, complete=True
        return Resp(200, {"import_id": "693fde90", "status": "completed",
                          "total_tracks": 18, "searched": 18, "queued": 0,
                          "completed": 14, "failed": 4, "skipped": 0,
                          "dupe_skipped": 0, "rate_limited": False,
                          "error": None,
                          "tracks": [{"artist": "The Fratellis - Mistress Mabel",
                                      "song": "Mistress Mabel", "status": "failed",
                                      "error": "Duration mismatch", "job_id": "j1"}],
                          "complete": True})
    if "/api/jobs/" in url:
        return Resp(200, {"id": "816f3ba5", "status": "completed",
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

# 2) search normalization (duration parsed, artist falls back to channel,
#    source_url kept for jiosaavn downloads)
token, results = MG.search("The Fratellis - Chelsea Dagger")
assert token == "tok-123" and len(results) == 3
r0, r2 = results[0], results[2]
assert r0["artist"] == "Paris Music" and r0["duration_secs"] == 228
assert r0["source_url"].startswith("https://aac.saavncdn.com/")
assert r2["artist"] == "The Fratellis" and r2["duration_secs"] == 230
assert r2["relevance"] == 150 and r0["quality_tier"] == 4
print("2) search normalization OK")

# 3) pick_result: artist query must NEVER pick the karaoke cover (names
#    the original artist in its title) nor the party-mix namesake — the
#    official video on rank 3 wins (both live cases from 2026-10-08)
pick = MG.pick_result("The Fratellis - Chelsea Dagger", results)
assert pick["video_id"] == "sEXHeTcxQy4", pick
# bare title (no artist tokens): MG's ranking decides among non-covers —
# documented limitation: a namesake can win here
pick = MG.pick_result("Chelsea Dagger", results)
assert pick["video_id"] == "js_hwoEqKC6"
# playlists are never picked
pl = dict(results[1], is_playlist=True)
assert MG.pick_result("x", [pl]) is None
print("3) pick_result (karaoke cover + namesake + bare title) OK")

# 4) download body carries source_url + the completeness-check pair
MG.download(results[2], token)
body = CALLS[-1]["json"]
assert body["download_type"] == "single" and body["source"] == "youtube"
assert body["source_url"].endswith("sEXHeTcxQy4")
assert body["search_token"] == "tok-123"
assert body["selected_duration_secs"] == 230
print("4) download body (source_url + token + duration) OK")

# 5) wait_for_job: completed / failed / timeout (string job ids are real)
job = MG.wait_for_job("816f3ba5", timeout=10)
assert job["status"] == "completed"
print("5a) wait_for_job completed OK")


def fail_route(method, url, json=None, timeout=None):
    return Resp(200, {"id": "78ab", "status": "failed",
                      "error": "Duration mismatch: got 99s"})


MG.requests.request = fail_route
try:
    MG.wait_for_job("78ab", timeout=5)
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
MG.requests.request = lambda *a, **kw: Resp(200, {"id": "79c", "status": "running"})
try:
    MG.wait_for_job("79c", timeout=10)
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

# 7) album client: resolve-release-group hands back the download fields
MG.requests.request = route
summary = MG.resolve_release_group("d8008a53-9c22-3468-b1f4-6dcbe1c87418")
assert summary["release_mbid"] == "6d566ef6-199d-47f0-9df3-64c1f6f51a38"
assert CALLS[-1]["json"] == {"release_group_mbid": "d8008a53-9c22-3468-b1f4-6dcbe1c87418"}
print("7) resolve_release_group OK")

# 8) download_album body (artist/album_title/release_mbid) + import_id
d = MG.download_album("The Fratellis", "Here We Stand", summary["release_mbid"])
assert d["import_id"] == "693fde90" and d["track_count"] == 18
body = CALLS[-1]["json"]
assert body["artist"] == "The Fratellis" and body["release_mbid"] == summary["release_mbid"]
MG.requests.request = lambda *a, **kw: Resp(200, {"track_count": 18})
try:
    MG.download_album("x", "y", "z")
    raise AssertionError("should have raised")
except MG.MGJobFailed:
    pass
MG.requests.request = route
print("8) download_album (body + missing import_id) OK")

# 9) import_status / wait_for_import: complete, PARTIAL SUCCESS (returned,
#    not raised), error status, timeout
st = MG.import_status("693fde90")
assert st["complete"] is True and st["completed"] == 14
result = MG.wait_for_import("693fde90", timeout=10)
assert result["completed"] == 14 and result["failed"] == 4  # partial: no raise
print("9a) import_status + wait_for_import partial success OK")


def error_route(method, url, json=None, timeout=None):
    return Resp(200, {"status": "error", "error": "tracklist gone", "complete": False})


MG.requests.request = error_route
try:
    MG.wait_for_import("abc", timeout=5)
    raise AssertionError("should have raised")
except MG.MGJobFailed as e:
    assert "tracklist gone" in str(e)
print("9b) wait_for_import error status -> MGJobFailed OK")

MG.requests.request = lambda *a, **kw: Resp(
    200, {"status": "processing", "complete": False})
try:
    MG.wait_for_import("abc", timeout=10)
    raise AssertionError("should have raised")
except MG.MGJobFailed as e:
    assert "not finished" in str(e)
print("9c) wait_for_import timeout -> MGJobFailed OK")
MG.requests.request = route

print("smoke_musicgrabber: all assertions passed")
