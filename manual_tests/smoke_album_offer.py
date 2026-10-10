# -*- coding: utf-8 -*-
"""Smoke test for the bot's album offer wiring (Story 2.5).

Run:  python manual_tests/smoke_album_offer.py
Simulates the full free-text-track→offer→album-job flow without Telegram,
MusicGrabber, beets or the job store: every collaborator is monkeypatched;
assertions check the offer buttons, the job payload, the message sequence
and the singleton cleanup.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import musik.bot as B  # noqa: E402
import musik.releases as R  # noqa: E402
from musik import jobs as jobs_mod  # noqa: E402
from musik import musicgrabber as MG  # noqa: E402

SENT: list = []
JOB_UPDATES: list[dict] = []
INGEST_RUNS: list[int] = [0]


# --- collaborators -------------------------------------------------------

CANDS = [
    {"rg_mbid": "rg-album", "artist": "Example Band", "title": "Great Album",
     "type": "album", "year": "2001", "score": 100, "in_library": False},
    {"rg_mbid": "rg-new", "artist": "Example Band", "title": "Reissue Era",
     "type": "album", "year": "2024", "score": 50, "in_library": True},
]

R.track_album_candidates = lambda artist, title, library=None, **kw: list(CANDS)


class FakeItem:
    def __init__(self, id, artist, title, added=1, mb_artistid="f4ccf6c5-x"):
        self.id, self.artist, self.title, self.added = id, artist, title, added
        self.album_id = None
        self.mb_artistid = mb_artistid


class FakeLib:
    def items(self, q):
        return [FakeItem(7, "Example Band", "Song")]

    def get_item(self, id):
        return FakeItem(id, "Example Band", "Song") if id == 7 else None


B._open_library = lambda: FakeLib()


def send(text, markup=None):
    SENT.append((text, markup))


jobs_mod.add_job = lambda text, chat_id: {"id": "job-1", "text": text,
                                          "chat_id": chat_id, "status": "queued"}
jobs_mod.update_job = lambda job_id, **fields: JOB_UPDATES.append(
    {"id": job_id, **fields})

MG.resolve_release_group = lambda rg: {
    "artist": "Example Band", "album_title": "Great Album",
    "release_mbid": "rel-1", "year": "2001", "track_count": 12}
MG.download_album = lambda artist, title, rel: {
    "import_id": "imp-1", "track_count": 12, "queued_count": 12}
MG.wait_for_import = lambda import_id, timeout=None, progress=None: (
    progress and progress({"completed": 6, "total_tracks": 12, "failed": 1}),
    {"completed": 11, "total_tracks": 12, "dupe_skipped": 1, "tracks": [
        {"status": "failed", "song": "Bonus", "artist": "Example Band"},
    ]})[1]

import musik.ingest as ingest_mod  # noqa: E402
import musik.plex as plex_mod  # noqa: E402

ingest_mod.cmd_ingest = lambda: INGEST_RUNS.__setitem__(0, INGEST_RUNS[0] + 1)
plex_mod.refresh_library = lambda: (True, "Plex-Scan angestoßen")

REMOVED: list[int] = []
B._remove_singleton = lambda item_id: (REMOVED.append(item_id),
                                       "Example Band - Song")[1]

# --- 1) offer construction ------------------------------------------------

job = {"id": "t1", "chat_id": 42, "kind": "search"}
pick = {"artist": "Example Band", "title": "Song"}
B._maybe_album_offer(job, "Example Band - Song", pick, send)
assert SENT, "offer message must be sent"
text, markup = SENT[-1]
buttons = [b for row in markup.inline_keyboard for b in row]
assert len(buttons) == 3, [b.text for b in buttons]
assert buttons[0].text.startswith("💿 Great Album (2001)")
assert buttons[1].text.startswith("💿 Reissue Era (2024) ✓"), buttons[1].text
assert buttons[2].callback_data.endswith(":no")
data0 = buttons[0].callback_data  # album:<seq>:0
assert data0.startswith("album:")
keys = set(B._ALBUM_OFFERS)
assert keys == {data0.split(":", 1)[1], buttons[1].callback_data.split(":", 1)[1],
                buttons[2].callback_data.split(":", 1)[1]}
print("1) offer buttons (icons, ✓, dismiss) + offer map OK")

# --- 2) tap → album job (what _on_album_callback enqueues) ---------------

offer = B._ALBUM_OFFERS.pop(data0.split(":", 1)[1])
assert offer["rg_mbid"] == "rg-album" and offer["singleton_id"] == 7
assert offer["track_artist"] == "Example Band" and offer["track_title"] == "Song"
album_job = {"id": "job-1", "chat_id": 42, "kind": "album", "album": offer}
print("2) offer payload (rg_mbid + singleton id + track identity) OK")

# --- 3) album job execution: messages, ingest, singleton removal ---------

SENT.clear()
B._execute_album(album_job, send)
joined = "\n".join(t for t, _m in SENT)
assert "löse das Release auf" in joined
assert "12 Track(s) via MusicGrabber" in joined
assert "6/12" in joined                 # progress line fired
assert "Import & Tagging" in joined
assert "11/12 Track(s) importiert" in joined
assert "Single-Version entfernt" in joined
assert "Bonus" in joined                # failed track named
assert "1 bereits vorhanden" in joined  # dupe_skipped surfaced
assert INGEST_RUNS[0] == 1 and REMOVED == [7]
assert JOB_UPDATES[-1]["status"] == "done"
mg_import = [u for u in JOB_UPDATES if "mg_import" in u]
assert mg_import and mg_import[0]["mg_import"]["import_id"] == "imp-1"
print("3) album job (resolve→download→progress→ingest→cleanup→summary) OK")

# --- 4) engine failure → no silent downgrade, Spotify hint ---------------

MG.wait_for_import = lambda *a, **kw: (_ for _ in ()).throw(
    MG.MGJobFailed("job imp-2 not finished within 3600s"))
SENT.clear()
B._execute_album(album_job, send)
joined = "\n".join(t for t, _m in SENT)
assert "fehlgeschlagen" in joined and "Spotify-Album-Link" in joined
assert JOB_UPDATES[-1]["status"] == "error"
print("4) album failure path (no engine downgrade, Spotify hint) OK")

print("smoke_album_offer: all assertions passed")
