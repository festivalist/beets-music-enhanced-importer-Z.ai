# -*- coding: utf-8 -*-
"""Smoke test for the ingest enrich gate (Story 9.7).

Run:  python manual_tests/smoke_enrich_gate.py
Outcome of the 2026-10-20 finding: _outcome listed ALL historical
auto/asis albums of a root — with 1000+ albums the enrich phase ran
~1000 beets subprocess pairs per cycle (>1 h) even when the cycle
imported NOTHING, keeping the ingest.lock busy quasi-continuously.
This test pins the gate: only units NOT already decided before the run
contribute album pairs; counts stay whole-root.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import musik.paths as paths_mod  # noqa: E402
from musik import ingest as ingest_mod  # noqa: E402
from musik import state as state_mod  # noqa: E402

# Plattformneutral (os.sep!): _outcome filtert mit Root-Prefix —
# Windows-Backslashes würden auf Linux nichts matchen.
ROOT = os.path.join("base", "stage")


def seed(path: str, status: str, artist: str, album: str) -> None:
    st = state_mod.load()
    state_mod.put_unit(st, {
        "path": path, "status": status, "reason": "", "updated": 0.0,
        "files": [os.path.join(path, "f1")],
        "chosen": {"artist": artist, "album": album}})
    state_mod.save(st)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        sd = os.path.join(tmp, "state")
        paths_mod.state_dir = lambda: sd

        seed(os.path.join(ROOT, "old"), "auto", "Old Artist", "Old Album")
        seed(os.path.join(ROOT, "old2"), "auto", "Old Artist 2", "Old Album 2")
        seed(os.path.join(ROOT, "hist"), "asis", "Hist Artist", "Hist Album")
        seed(os.path.join(ROOT, "rev"), "review", "Rev Artist", "Rev Album")
        seed(os.path.join(ROOT, "new"), "auto", "New Artist", "New Album")

        # Gate: nur Units, die NICHT vor dem Lauf entschieden waren
        pre = {os.path.normcase(os.path.normpath(os.path.join(ROOT, n)))
               for n in ("old", "old2", "hist")}
        counts, albums = ingest_mod._outcome(ROOT, only_new_vs=pre)
        assert albums == [("New Artist", "New Album")], albums

        # counts bleiben Whole-Root (Journal-Zeile unverändert)
        assert counts.get("auto") == 3 and counts.get("asis") == 1, counts
        assert counts.get("review") == 1, counts

        # Ohne Gate (Rückwärtskompatibilität): alle Alben
        counts, albums = ingest_mod._outcome(ROOT)
        assert len(albums) == 4, albums

        # Singleton-Units zählen weiter nicht (Historie unverändert)
        seed(ROOT + r"\sing", "auto", "Sing Artist", "Sing Album")

    print("smoke_enrich_gate: alle Assertionen grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
