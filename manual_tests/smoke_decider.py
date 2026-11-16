# -*- coding: utf-8 -*-
"""Smoke test for the Decider's forced/override application paths and the
hardened fetch subprocess deadline.

Run:  python manual_tests/smoke_decider.py
Pure logic with fake candidates/matches — no beets lookups, no network.

Covers the 2026-10-08 P1 fixes (EPIC 6.1):
- 6.1a: the override search result must be attached to task.candidates so
  MusikSession._match_for resolves it — previously the fallback silently
  applied the rejected top candidate (or crashed via Action.SKIP).
- 6.1c: _run_logged kills a SILENT stalled child at the deadline (the old
  line-driven check never fired without output).
"""

import os
import sys
import tempfile
import time
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from musik.session import Decider, MusikSession, NetworkErrorRecorder  # noqa: E402


class FakeDist(dict):
    def __float__(self):
        return sum(self.values())


def fake_match(artist, album, id_, distance_pen=0.30):
    info = types.SimpleNamespace(
        data_source="MusicBrainz", artist=artist, artists=[artist],
        album=album, album_id=id_, track_id=id_, year=None, tracks=[],
        title=album,
    )
    return types.SimpleNamespace(
        info=info, distance=FakeDist({"album": distance_pen}),
        mapping={}, extra_items=[],
    )


def fake_task(candidates, artist="Some Artist", album="Some Album"):
    return types.SimpleNamespace(
        rec=None, candidates=list(candidates), items=[],
        cur_artist=artist, cur_album=album, paths=[b"x"],
    )


netrec = NetworkErrorRecorder()

# 1) override: the search result must become resolvable via _match_for
import musik.session as S  # noqa: E402

rejected = fake_match("Wrong Artist", "Wrong Album", "id-rejected")
override = fake_match("Real Artist", "Real Album", "id-override", 0.01)
task = fake_task([rejected])
S.tag_album_compat = lambda items, **kw: types.SimpleNamespace(
    candidates=[override])
dec = Decider(netrec, auto_accept_distance=0.25,
              override_artist="Real Artist", override_album="Real Album")
action, record = dec.decide_album(task)
assert action == "apply" and record["status"] == "review-apply", (action, record)
assert task.candidates[0] is override, "override result must lead task.candidates"
sess = MusikSession.__new__(MusikSession)   # _match_for needs no instance state
match = sess._match_for(task, record)
assert match is override, f"_match_for resolved {match!r}, not the override result"
print("1) override result attached and resolved OK (EPIC 6.1a)")

# 2) override from an EMPTY candidate list (formerly the SKIP-crash path)
task2 = fake_task([])
dec2 = Decider(netrec, auto_accept_distance=0.25,
               override_artist="Real Artist", override_album="Real Album")
action2, _record2 = dec2.decide_album(task2)
assert action2 == "apply" and task2.candidates[0] is override
print("2) override from empty candidate list OK (no SKIP crash)")

# 3) _run_logged: a SILENT child must die at the deadline
from musik import fetch as F  # noqa: E402

tmp = tempfile.mkdtemp()
job = F.FetchJob(
    job_id="smoke-timeout", kind="search", tool="somedl", query="x",
    job_dir=tmp, log_path=os.path.join(tmp, "job.log"),
)
start = time.monotonic()
rc = F._run_logged(
    [sys.executable, "-c", "import time; time.sleep(60)"],
    job.log_path, job, deadline_s=time.monotonic() + 2,
)
elapsed = time.monotonic() - start
assert job.timed_out, "silent child must be recognized as timed out"
assert elapsed < 30, f"deadline not enforced (elapsed {elapsed:.1f}s)"
assert "time budget" in (job.errors[-1] if job.errors else "")
print(f"3) silent child killed at deadline OK (rc={rc}, {elapsed:.1f}s, EPIC 6.1c)")

# 4) int ids (Story 9.8): Discogs-Kandidaten tragen int album/track ids —
#    der Forced-Pfad muss koerzieren statt im UUID-Regex zu crashen
#    ("expected string or bytes-like object, got 'int'", 2026-10-20).
from musik import review as R  # noqa: E402

dec_int = Decider(netrec, auto_accept_distance=0.25, forced_album_id=2516185)
assert dec_int._normalize_id(2516185) == "2516185"
cand_int = fake_match("Traffic", "Traffic", 2516185)
action4, record4 = dec_int.decide_album(fake_task([cand_int]))
assert action4 == "apply" and record4["status"] == "review-apply", \
    (action4, record4)

u_int = {"candidates": [{"id": 2516185}, {"id": None}, {"album": "no id"}]}
assert R.cand_id(u_int, 1) == "2516185", R.cand_id(u_int, 1)
assert R.cand_id(u_int, 2) == ""
assert R.cand_id(u_int, 3) == ""
print("4) int candidate ids tolerated end-to-end OK (Story 9.8)")

# 5) Story 2.3: singleton cross-engine dedup — same normalized
#    artist+title within the duration grace duplicates, different
#    recordings (bigger duration gap) pass
sess = MusikSession.__new__(MusikSession)


class _OldItem:
    artist, title, length = "a", "t", 201.0
    path = b"/x/old.mp3"


class _FakeLib:
    def __init__(self, items):
        self._items = items

    def items(self):
        return list(self._items)


sess.lib = _FakeLib([_OldItem()])
sess.duplicate_losers = []
task5 = types.SimpleNamespace(item=types.SimpleNamespace(
    path=b"/x/new.mp3", artist="A", title="T", length=200.0))
match5 = types.SimpleNamespace(info=types.SimpleNamespace(artist="A", title="T"))
assert sess._singleton_dupe(task5, match5) is True, "same song must dedup"
assert sess.duplicate_losers == [], "skipped file not on disk: nothing to trash"

sess2 = MusikSession.__new__(MusikSession)
sess2.lib = _FakeLib([types.SimpleNamespace(
    artist="a", title="t", length=260.0, path=b"/x/live.mp3")])
sess2.duplicate_losers = []
assert sess2._singleton_dupe(task5, match5) is False, "live version passes"
assert sess2.duplicate_losers == []
print("5) singleton cross-engine dedup OK (Story 2.3)")

# --- Entscheidungsmatrix (Story 6.6) --------------------------------------
# Die Standard-Pfade von decide_album mit Kandidaten: auto-apply / review /
# tier-3 asis (Distanz) / tier-3 asis (Kontradiktion) / network / forced-miss.
import os as _os  # noqa: E402
import tempfile as _tempfile  # noqa: E402

from musik import scan as scan_mod  # noqa: E402

_tmp = _tempfile.mkdtemp()
_TAGS: dict[str, dict[str, str]] = {}


def fake_tag(f, field):
    return _TAGS.get(_os.path.normcase(f), {}).get(field, "")


scan_mod.tag_of = fake_tag   # scan.tags_complete liest über scan-Globals


def tagged_unit(dir_name: str, artist: str, album: str) -> dict:
    d = _os.path.join(_tmp, dir_name)
    _os.makedirs(d, exist_ok=True)
    files = []
    for n in ("01.mp3", "02.mp3"):
        fp = _os.path.join(d, n)
        open(fp, "wb").close()
        _TAGS[_os.path.normcase(fp)] = {
            "artist": artist, "albumartist": artist,
            "album": album, "title": "t" + n,
        }
        files.append(fp)
    return {
        "path": d, "files": files, "n_files": 2,
        "singleton": False, "split_into_singletons": False,
        "guessed": {"artist": artist, "album": album},
        "hints": [], "artists_seen": [artist.lower()],
    }


# M1) starker Kandidat (Namen ident, Distanz 0.01) -> apply/auto
dec = Decider(NetworkErrorRecorder(), auto_accept_distance=0.25,
              unit=tagged_unit("m1", "Some Artist", "Some Album"))
good = fake_match("Some Artist", "Some Album", "id-good", 0.01)
action, record = dec.decide_album(fake_task([good]))
assert action == "apply" and record["status"] == "auto", (action, record)
print("M1) strong match -> apply/auto OK")

# M2) einziger Kandidat ueber der Auto-Distanz, aber unter dem Tier-3-Floor
#     -> skip/review ("below auto-accept confidence")
dec = Decider(NetworkErrorRecorder(), auto_accept_distance=0.25,
              unit={"files": [], "singleton": False, "guessed": {},
                    "hints": [], "artists_seen": []})
weak = fake_match("Some Artist", "Some Album", "id-weak", 0.30)
action, record = dec.decide_album(fake_task([weak]))
assert action == "skip" and record["status"] == "review", (action, record)
assert record["reason"].startswith("below auto-accept confidence"), record
assert record["candidates"], "review record must carry previews"
print("M2) weak match -> review with blocker OK")

# M3) alles ueber dem Tier-3-Floor + eigene Tags vollstaendig + Ordner
#     stimmt -> apply-asis (tier 3, Distanz-Pfad)
dec = Decider(NetworkErrorRecorder(), auto_accept_distance=0.25,
              unit=tagged_unit("m3", "Real Artist", "Real Album"))
garbage = fake_match("Other Band", "Other Record", "id-garbage", 0.50)
action, record = dec.decide_album(fake_task([garbage],
                                            artist="Real Artist",
                                            album="Real Album"))
assert action == "apply-asis" and record["status"] == "asis", (action, record)
assert "folder and tags agree" in record["reason"], record
print("M3) distance-flood -> tier-3 asis OK")

# M4) ALLE Top-Kandidaten widersprechen der Identitaet (Artist/Title-Ebene)
#     -> apply-asis per Nutzer-Regel (2026-09-17), nicht review
dec = Decider(NetworkErrorRecorder(), auto_accept_distance=0.25,
              unit=tagged_unit("m4", "Real Artist", "Real Album"))
wrong = [fake_match(f"Wrong {i}", f"Also Wrong {i}", f"id-w{i}", 0.01)
         for i in range(3)]
action, record = dec.decide_album(fake_task(wrong, artist="Real Artist",
                                            album="Real Album"))
assert action == "apply-asis" and record["status"] == "asis", (action, record)
assert "all top candidates contradict" in record["reason"], record
print("M4) all top candidates contradict -> asis by user rule OK")

# M5) keine Kandidaten + MusicBrainz-Fehler im Recorder -> skip/network
#     (NIE "keine Antwort" als unmatched verkaufen)
recorder = NetworkErrorRecorder()
recorder.snapshot = lambda: [("musicbrainz.mb2", "HTTP 503: busy")]
dec = Decider(recorder, auto_accept_distance=0.25,
              unit={"files": [], "singleton": False, "guessed": {},
                    "hints": [], "artists_seen": []})
action, record = dec.decide_album(fake_task([]))
assert action == "skip" and record["status"] == "network", (action, record)
assert "MusicBrainz lookup failed" in record["reason"], record
print("M5) MB error -> network, not unmatched OK")

# M6) forced id kam im Text-Search nicht zurueck und liefert auch per
#     search_ids nichts -> skip/review ("forced id ... not among candidates")
dec = Decider(NetworkErrorRecorder(), auto_accept_distance=0.25,
              forced_album_id="11111111-1111-1111-1111-111111111111")
S.tag_album_compat = lambda items, **kw: types.SimpleNamespace(candidates=[])
present = fake_match("Some Artist", "Some Album", "id-other", 0.01)
action, record = dec.decide_album(fake_task([present]))
assert action == "skip" and record["status"] == "review", (action, record)
assert "not among candidates" in record["reason"], record
print("M6) forced id miss -> clean review skip OK")

print("smoke_decider: all assertions passed")
