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
S.tag_album = lambda items, **kw: (
    "Real Artist", "Real Album", types.SimpleNamespace(candidates=[override]))
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

print("smoke_decider: all assertions passed")
