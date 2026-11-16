# -*- coding: utf-8 -*-
"""Smoke test for the action spool (Story 9.6 + 10.10, Import-Monitor).

Run:  python manual_tests/smoke_spool.py
Covers add/take roundtrips, the take-then-add race pattern (a new entry
written during a drain survives), flip_retry against seeded state, and
drain_and_execute with a mocked review/asis layer: entries execute, the
associated job records get the REAL outcome, the spool ends empty.
Story 10.10: applies whose PRECONDITION failed transiently (unit
unknown/pending, asis gate still blocking) return to the spool with
attempts+1 up to MAX_ATTEMPTS, then decay with an explicit note; terminal
outcomes consume the decision; open_actions() feeds the snapshot counter.
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


def seed_unit(path, status, files=None):
    st = state_mod.load()
    state_mod.put_unit(st, {"path": path, "status": status, "reason": "",
                            "updated": time.time(),
                            "files": files or [path + r"\f"]})
    state_mod.save(st)


def unit_status(path):
    u = state_mod.get_unit(state_mod.load(), path)
    return (u or {}).get("status")


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
        assert all(e.get("attempts") == 0 for e in entries), entries
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
        #    bekommen das echte Ergebnis, Spool endet leer. asis-Mock
        #    setzt die Unit simuliert auf asis (End-Status → konsumiert).
        class _FakeConf:
            def __getitem__(self, key):
                return SimpleNamespace(
                    as_filename=lambda: os.path.join(tmp, f"{key}.fake"))

        beets.config = _FakeConf()
        import beets.library as beets_library
        beets_library.Library = lambda *a, **k: SimpleNamespace()

        def _import_ok(paths, progress=None):
            for p in paths:
                seed_unit(p, "asis")
            return [f"✅ {p} — importiert" for p in paths], False

        review_mod.apply_decisions_rows = lambda rows: (
            1, [f"angewandt für {rows[0]['unit_path']}"])
        asis_mod.import_units = _import_ok

        jobs_mod.add_job("Monitor-Review", 0)   # id unbekannt → via add
        all_jobs = jobs_mod.load_jobs()
        jid_review = all_jobs[-1]["id"]
        jid_asis = jobs_mod.add_job("Monitor-Asis", 0)["id"]
        seed_unit(r"C:\r\rev", "review")
        seed_unit(r"C:\r\done", "review")
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

        # --- Story 10.10: transient gescheiterte Applies kehren zurück --

        # 5) asis am Gate gescheitert (Valli-Fall: Unit bleibt review):
        #    Eintrag kehrt mit attempts=1 zurück, Job bleibt offen
        stuck = r"C:\r\stuck"
        seed_unit(stuck, "review")

        def _import_gate_fail(paths, progress=None):
            return [f"⚠️ {p} — Status jetzt „review“" for p in paths], False

        asis_mod.import_units = _import_gate_fail
        jid_stuck = jobs_mod.add_job("Monitor-Asis stuck", 0)["id"]
        spool_mod.add("asis", jid_stuck, {"unit_paths": [stuck]})
        logs3: list[str] = []
        assert spool_mod.drain_and_execute(log=logs3.append) == 1
        again = spool_mod.take()
        assert len(again) == 1 and again[0]["attempts"] == 1, again
        assert again[0]["payload"]["unit_paths"] == [stuck], again
        assert jobs_mod.get_job(jid_stuck)["status"] == "queued", \
            jobs_mod.get_job(jid_stuck)
        assert unit_status(stuck) == "review"
        assert any("[retry]" in l for l in logs3), logs3
        # Reparatur greift nachträglich → nächster Zyklus konsumiert
        spool_mod.add("asis", jid_stuck, {"unit_paths": [stuck]},
                      attempts=1)
        asis_mod.import_units = _import_ok
        logs4: list[str] = []
        assert spool_mod.drain_and_execute(log=logs4.append) == 1
        assert spool_mod.take() == [], "Retry-Eintrag nicht konsumiert"
        assert jobs_mod.get_job(jid_stuck)["status"] == "done"
        assert unit_status(stuck) == "asis"

        # 6) Versuchsgrenze: attempts=MAX → verfällt mit Hinweis,
        #    Job error, Spool leer (kein Endlos-Reenqueue)
        seed_unit(stuck, "review")
        asis_mod.import_units = _import_gate_fail
        jid_decay = jobs_mod.add_job("Monitor-Asis decay", 0)["id"]
        spool_mod.add("asis", jid_decay, {"unit_paths": [stuck]},
                      attempts=spool_mod.MAX_ATTEMPTS)
        logs5: list[str] = []
        assert spool_mod.drain_and_execute(log=logs5.append) == 1
        assert spool_mod.take() == [], "verfallener Eintrag kehrte zurück!"
        jd = jobs_mod.get_job(jid_decay)
        assert jd["status"] == "error" and "verfällt" in jd["summary"], jd
        assert unit_status(stuck) == "review"  # unangetastet

        # 7) gemischter asis-Batch: Import greift nur für einen Pfad —
        #    Job done (partial), nur der offene Pfad kehrt zurück
        seed_unit(r"C:\r\ok2", "review")
        seed_unit(stuck, "review")

        def _import_mixed(paths, progress=None):
            seed_unit(paths[0], "asis")
            return ([f"✅ {paths[0]} — importiert",
                     f"⚠️ {paths[1]} — Status jetzt „review“"], False)

        asis_mod.import_units = _import_mixed
        jid_mix = jobs_mod.add_job("Monitor-Asis mix", 0)["id"]
        spool_mod.add("asis", jid_mix,
                      {"unit_paths": [r"C:\r\ok2", stuck]})
        assert spool_mod.drain_and_execute(log=logs5.append) == 1
        again = spool_mod.take()
        assert len(again) == 1, again
        assert again[0]["payload"]["unit_paths"] == [stuck], again
        assert jobs_mod.get_job(jid_mix)["status"] == "done"
        assert unit_status(r"C:\r\ok2") == "asis"

        # 8) review-Row auf pending-Unit (transient): Row kehrt zurück;
        #    applied=0 → Job queued. Danach wird die Unit reviewable
        #    → Apply läuft, konsumiert.
        review_mod.apply_decisions_rows = lambda rows: (
            0, [f"nicht reviewbar (Status pending): {rows[0]['unit_path']}"])
        seed_unit(r"C:\r\pen", "pending")
        jid_pen = jobs_mod.add_job("Monitor-Review pending", 0)["id"]
        spool_mod.add("review", jid_pen,
                      {"decisions": [{"unit_path": r"C:\r\pen",
                                      "decision": "accept"}]})
        logs6: list[str] = []
        assert spool_mod.drain_and_execute(log=logs6.append) == 1
        again = spool_mod.take()
        assert len(again) == 1 and again[0]["attempts"] == 1, again
        assert jobs_mod.get_job(jid_pen)["status"] == "queued"
        spool_mod.add(again[0]["kind"], again[0]["job_id"],
                      again[0]["payload"], attempts=1)
        seed_unit(r"C:\r\pen", "review")
        review_mod.apply_decisions_rows = lambda rows: (
            1, [f"angewandt für {rows[0]['unit_path']}"])
        assert spool_mod.drain_and_execute(log=logs6.append) == 1
        assert spool_mod.take() == []
        assert jobs_mod.get_job(jid_pen)["status"] == "done"

        # 9) review-Row, deren Apply deterministisch wieder in review
        #    landet: KEIN Retry (Forced-Pfad ist deterministisch)
        review_mod.apply_decisions_rows = lambda rows: (
            1, [f"angewandt für {rows[0]['unit_path']}"])
        seed_unit(r"C:\r\back", "review")
        jid_back = jobs_mod.add_job("Monitor-Review back-to-review", 0)["id"]
        spool_mod.add("review", jid_back,
                      {"decisions": [{"unit_path": r"C:\r\back",
                                      "decision": "accept"}]})
        assert spool_mod.drain_and_execute(log=logs6.append) == 1
        assert spool_mod.take() == [], "deterministisches Ergebnis re-spooled"
        assert jobs_mod.get_job(jid_back)["status"] == "done"

        # 10) open_actions() liefert die Snapshot-Sicht; der Monitor
        #     zeigt den Zähler
        seed_unit(r"C:\r\stuck2", "review")
        jid_open = jobs_mod.add_job("Monitor-Asis open", 0)["id"]
        spool_mod.add("asis", jid_open, {"unit_paths": [r"C:\r\stuck2"]})
        o = spool_mod.open_actions()
        assert o["open"] == 1 and o["oldest_queued"], o
        assert o["max_attempts"] == 0, o
        with open(os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "musik", "monitor.html"),
                encoding="utf-8") as fh:
            mon = fh.read()
        assert "snap.spool" in mon and "offene Nutzer-Entscheidungen" in mon
        assert spool_mod.drain_and_execute(log=logs6.append) == 1
        assert spool_mod.take() == []

    print("smoke_spool: alle Assertionen grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
