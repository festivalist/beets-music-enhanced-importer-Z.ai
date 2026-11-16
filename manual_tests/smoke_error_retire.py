# -*- coding: utf-8 -*-
"""Smoke test for error-unit retirement on vanished files (Story 6.9).

Run:  python manual_tests/smoke_error_retire.py
Error units are retryable via flip_retry — but once their source files
are gone (live case: the 1001-Albums G.-Love unit whose files the
mega-cycle imported while the unit stayed `error` from an old IndexError),
a retry has nothing left to work with and the unit lingers forever.
A scan must retire such units to `ignored`, while error units whose
files still exist stay retryable.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from musik import scan as S  # noqa: E402


def seed(base: str, units: dict) -> str:
    sd = os.path.join(base, "state")
    os.makedirs(sd, exist_ok=True)
    with open(os.path.join(sd, "state.json"), "w", encoding="utf-8") as fh:
        json.dump({"meta": {}, "units": units}, fh)
    return sd


def unit(path: str, status: str, files: list) -> dict:
    return {"path": path, "status": status, "reason": "IndexError: ...",
            "updated": 1000.0, "files": files, "n_files": len(files),
            "kind": "album", "source": "scan", "hints": [],
            "artists_seen": [], "guessed": {}}


def case1_error_with_gone_files_retires():
    base = tempfile.mkdtemp(prefix="smoke-er-")
    # die Pipeline normcased Unit-Keys (state.put_unit) — der Seed muss
    # dasselbe Format nutzen, sonst matchen root_key-Vergleiche nie
    u1key = os.path.normcase(os.path.normpath(os.path.join(base, "u1")))
    gone = unit(u1key, "error", [os.path.join(base, "u1", "a.mp3")])
    sd = seed(base, {u1key: gone})
    import musik.paths as paths_mod
    paths_mod.state_dir = lambda: sd  # type: ignore  (state.py ruft zur Laufzeit)
    os.makedirs(os.path.join(base, "u2"), exist_ok=True)
    # Scan-Root mit einer echten Datei, damit classify etwas findet
    open(os.path.join(base, "u2", "b.mp3"), "wb").close()
    S.cmd_scan(base)
    st2 = json.load(open(os.path.join(sd, "state.json"), encoding="utf-8"))
    u1 = st2["units"][u1key]
    assert u1["status"] == "ignored", u1["status"]
    assert "no longer exist" in u1["reason"], u1["reason"]
    print("1) error unit + verschwundene Dateien -> ignored OK")


if __name__ == "__main__":
    case1_error_with_gone_files_retires()
    print("smoke_error_retire: alle Assertionen grün")
