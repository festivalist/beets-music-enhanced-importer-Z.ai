# -*- coding: utf-8 -*-
"""Smoke test for the /status timer-ingest summary (Story 9.2).

Run:  python manual_tests/smoke_status_state.py
Seeds a temp state.json and checks the /status extension: unit counts in
stable order, review-stau callout, relative last-change age, empty-state
silence, and the ingest.lock probe (None → "unbekannt" on Windows-Dev
without fcntl).
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import musik.bot as B  # noqa: E402


def seed(base: str, units: dict) -> str:
    sd = os.path.join(base, "state")
    os.makedirs(sd, exist_ok=True)
    with open(os.path.join(sd, "state.json"), "w", encoding="utf-8") as fh:
        json.dump({"meta": {}, "units": units}, fh)
    return sd


def unit(path: str, status: str, updated: float) -> dict:
    return {"path": path, "status": status, "reason": "",
            "updated": updated}


def main() -> int:
    now = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        # 1) Counts in fester Reihenfolge + Review-Stau + letzter Change
        sd = seed(tmp, {
            r"C:\a": unit(r"C:\a", "auto", now - 3600),
            r"C:\b": unit(r"C:\b", "auto", now - 60),
            r"C:\c": unit(r"C:\c", "review", now - 7200),
            r"C:\d": unit(r"C:\d", "error", now - 30),
        })
        out = B._ingest_state_lines(sd)
        lines = out.splitlines()
        assert "4 Unit(s)" in lines[0], lines
        assert "2 auto" in lines[0], lines
        assert "1 review" in lines[0], lines
        assert "1 error" in lines[0], lines
        assert "gerade eben" in lines[0], lines   # max(updated) = now-30
        assert any("Review-Stau: 1" in l for l in lines), out

        # 2) Fehlende oder leere state.json → gar keine Zeilen
        assert B._ingest_state_lines(os.path.join(tmp, "fehlt")) == ""
        assert B._ingest_state_lines(seed(tmp, {})) == ""

        # 3) Lock-Probe: mit fcntl auf freiem Lock → nicht „läuft gerade“;
        #    ohne fcntl (Windows-Dev) → None → „unbekannt“-Vermerk
        sd = seed(tmp, {
            r"C:\a": unit(r"C:\a", "auto", now - 3600),
            r"C:\c": unit(r"C:\c", "review", now - 7200),
        })
        busy = B._ingest_busy(sd)
        out2 = B._ingest_state_lines(sd)
        try:
            import fcntl  # noqa: F401
            assert busy is False, busy
            assert "läuft gerade" not in out2, out2
        except ImportError:
            assert busy is None, busy
            assert "unbekannt (Windows-Dev)" in out2, out2

    print("smoke_status_state: alle Assertionen grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
