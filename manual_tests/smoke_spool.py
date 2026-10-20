# -*- coding: utf-8 -*-
"""Smoke test for the action spool (Story 9.6, Import-Monitor).

Run:  python manual_tests/smoke_spool.py
Covers add/take roundtrips, the take-then-add race pattern (a new entry
written during a drain survives), flip_retry against seeded state, and
drain_and_execute with a mocked review/asis layer: entries execute, the
associated job records get the REAL outcome, the spool ends empty.
"""

import json
import os
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import beets  # noqa: E402
import musik.paths as paths_mod  # noqa: E402
from musik import asis as asis_mod  # noqa: E402
from musik import jobs as jobs_mod  # noqa: E402
from musik import report as report_mod  # noqa: E402
from musik import review as review_mod  # noqa: E402
from musik import spool as spool_mod  # noqa: E402
from musik import state as state_mod  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        sd = os.path.join(tmp, "state")
        rd = os.path.join(tmp, "reports")
        os.makedirs(rd)
        paths_mod.state_dir = lambda: sd
        paths_mod.reports_dir = lambda: rd
        report_mod.reports_dir = lambda: rd  # Module-Bindung in report.py
        jobs_mod.state_dir = lambda: sd      # Module-Bindung in jobs.py
        spool_mod.state_dir = lambda: sd     # Module-Bindung in spool.py

        # 1) add/take Roundtrip + Race-Muster: Eintrag während der
        #    Entnahme überlebt (take() legt den leeren Spool nur an,
        #    wenn nicht inzwischen schon wieder einer existiert)
        assert spool_mod.take() == []
        spool_mod.add("review", "job-1", {"decisions": [{"x": 1}]})
        spool_mod.add("asis", "job-2", {"unit_paths": ["p"]})
        entries = spool_mod.take()
        assert [e["kind"] for e in entries] == ["review", "asis"], entries
        spool_mod.add("retry", "job-3", {"unit_paths": []})
        assert len(spool_mod.take()) == 1, "job-3 verloren!"

        # 2) flip_retry: network → pending, gezielt + global
        st = {"meta": {}, "units": {}}
        now = time.time()
        for p, s in ((r"C:\r\net1", "network"), (r"C:\r\net2", "network"),
                     (r"C:\r\rev", "review")):
            state_mod.put_unit(st, {"path": p, "status": s, "reason": "",
                                    "updated": now, "files": [p + "\\f"]})
        state_mod.save(st)
        assert spool_mod.flip_retry([r"C:\r\net1"]) == 1
        fresh = state_mod.get_unit(state_mod.load(), r"C:\r\net1")
        assert fresh["status"] == "pending", fresh
        assert state_mod.get_unit(state_mod.load(), r"C:\r\net2")[
            "status"] == "network"
        assert spool_mod.flip_retry([]) == 1  # Rest-network global

        # 3) drain_and_execute: gemockter review/asis-Layer, Job-Records
        #    bekommen das echte Ergebnis, Spool endet leer
        class _FakeConf:
            def __getitem__(self, key):
                return SimpleNamespace(
                    as_filename=lambda: os.path.join(tmp, f"{key}.fake"))

        beets.config = _FakeConf()
        import beets.library as beets_library
        beets_library.Library = lambda *a, **k: SimpleNamespace()
        review_mod.apply_decisions_rows = lambda rows: (
            1, [f"angewandt für {rows[0]['unit_path']}"])
        asis_mod.import_units = lambda paths, progress=None: (
            [f"✅ {p} — importiert" for p in paths], False)

        jobs_mod.add_job("Monitor-Review", 0)   # id unbekannt → via add
        all_jobs = jobs_mod.load_jobs()
        jid_review = all_jobs[-1]["id"]
        jid_asis = jobs_mod.add_job("Monitor-Asis", 0)["id"]
        spool_mod.add("review", jid_review,
                      {"decisions": [{"unit_path": r"C:\r\rev",
                                      "decision": "accept"}]})
        spool_mod.add("asis", jid_asis, {"unit_paths": [r"C:\r\done"]})

        logs: list[str] = []
        assert spool_mod.drain_and_execute(log=logs.append) == 2
        assert spool_mod.take() == [], "Spool nicht geleert"
        jr = jobs_mod.get_job(jid_review)
        assert jr["status"] == "done" and "nachgereicht" in jr["summary"], jr
        ja = jobs_mod.get_job(jid_asis)
        assert ja["status"] == "done" and "importiert" in ja["summary"], ja
        assert any("spool: 2" in l for l in logs), logs

        # 4) Fehlerfall: Exception in der Ausführung → Job error, Spool leer
        review_mod.apply_decisions_rows = lambda rows: 1 // 0
        spool_mod.add("review", jid_review, {"decisions": []})
        logs2: list[str] = []
        assert spool_mod.drain_and_execute(log=logs2.append) == 1
        assert jobs_mod.get_job(jid_review)["status"] == "error"
        assert spool_mod.take() == []

    print("smoke_spool: alle Assertionen grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
