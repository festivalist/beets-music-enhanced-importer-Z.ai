# -*- coding: utf-8 -*-
"""Smoke test for the per-row review-apply API (Story 9.5, Import-Monitor).

Run:  python manual_tests/smoke_review_apply_rows.py
Exercises review.apply_decisions_rows with a fully mocked engine/beets
layer against a seeded temp state: accept/accept2 force the right
candidate ids, ignore flips status, unknown units/decisions and
non-reviewable statuses are skipped with messages, singleton-override
guard, and the CSV/report writers run against a patched reports dir.
"""

import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import beets  # noqa: E402
import musik.paths as paths_mod  # noqa: E402
from musik import engine as engine_mod  # noqa: E402
from musik import report as report_mod  # noqa: E402
from musik import review as review_mod  # noqa: E402
from musik import state as state_mod  # noqa: E402

CALLS: list[dict] = []


def fake_run_unit_real(lib, unit, decider):
    CALLS.append({"forced": decider[1], "path": unit["path"]})
    return {"status": "auto", "reason": ""}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        sd = os.path.join(tmp, "state")
        rd = os.path.join(tmp, "reports")
        os.makedirs(rd)
        paths_mod.state_dir = lambda: sd
        paths_mod.reports_dir = lambda: rd
        report_mod.reports_dir = lambda: rd  # Module-Bindung in report.py

        # beets-Layer mocken (Library/config dürfen kein echtes Setup anfassen)
        class _FakeConf:
            def __getitem__(self, key):
                return SimpleNamespace(
                    as_filename=lambda: os.path.join(tmp, f"{key}.fake"))

        beets.config = _FakeConf()
        import beets.library as beets_library
        beets_library.Library = lambda *a, **k: SimpleNamespace()
        engine_mod.setup_beets = lambda: None
        engine_mod.build_decider = lambda unit, forced=None, lib=None: ("decider", forced)
        engine_mod.run_unit_real = fake_run_unit_real
        engine_mod.netrec = SimpleNamespace(clear=lambda: None)
        engine_mod._merge_result = lambda unit, outcome: None

        st = {"meta": {}, "units": {}}
        for path, status, extra in (
                (r"C:\r\beta", "review", {}),
                (r"C:\r\gamma", "review", {"singleton": True}),
                (r"C:\r\delta", "auto", {}),
                (r"C:\r\epsilon", "review", {}),
                (r"C:\r\zeta", "review", {"singleton": True}),
        ):
            unit = {"path": path, "status": status, "reason": "",
                    "updated": 0.0, "files": [path + "\\f1"],
                    "import_path": path + "\\imported"}
            unit.update(extra)
            state_mod.put_unit(st, unit)
        state_mod.put_unit(st, {
            "path": r"C:\r\alpha", "status": "review", "reason": "",
            "updated": 0.0, "files": [r"C:\r\alpha\f1"],
            "import_path": r"C:\r\alpha\imported",
            "candidates": [
                {"id": "cand-1", "artist": "A", "album": "Alpha",
                 "year": "2001", "distance": 0.1, "source": "mb"},
                {"id": "cand-2", "artist": "B", "album": "Beta",
                 "year": "2002", "distance": 0.2, "source": "mb"}]})
        state_mod.put_unit(st, {
            "path": r"C:\r\beta", "status": "review", "reason": "",
            "updated": 0.0, "files": [r"C:\r\beta\f1"],
            "import_path": r"C:\r\beta\imported",
            "candidates": [
                {"id": "beta-1", "artist": "C", "album": "Gamma",
                 "year": "2003", "distance": 0.3, "source": "mb"},
                {"id": "beta-2", "artist": "D", "album": "Delta",
                 "year": "2004", "distance": 0.4, "source": "mb"}]})
        state_mod.save(st)

        # 1) accept → Kandidat 1; accept2 → Kandidat 2
        applied, msgs = review_mod.apply_decisions_rows([
            {"unit_path": r"C:\r\alpha", "decision": "accept"},
            {"unit_path": r"C:\r\beta", "decision": "accept2"},
        ])
        assert applied == 2, (applied, msgs)
        assert CALLS[0]["forced"]["album_id"] == "cand-1", CALLS
        assert CALLS[1]["forced"]["album_id"] == "beta-2", CALLS
        assert any("angewandt [auto]" in m for m in msgs), msgs
        fresh = state_mod.get_unit(state_mod.load(), r"C:\r\alpha")
        assert fresh["status"] == "auto", fresh

        # 2) ignore → Statuswechsel ohne Engine-Aufruf
        calls_before = len(CALLS)
        applied, msgs = review_mod.apply_decisions_rows(
            [{"unit_path": r"C:\r\gamma", "decision": "ignore"}])
        assert applied == 1 and len(CALLS) == calls_before, (applied, msgs)
        assert state_mod.get_unit(state_mod.load(),
                                  r"C:\r\gamma")["status"] == "ignored"

        # 3) Abfänger: unbekannte Unit, falsches Vokabular, nicht
        #    reviewbarer Status, Singleton-Override ohne MBID
        applied, msgs = review_mod.apply_decisions_rows([
            {"unit_path": r"C:\r\fehlt", "decision": "accept"},
            {"unit_path": r"C:\r\delta", "decision": "accept"},
            {"unit_path": r"C:\r\epsilon", "decision": "hokuspokus"},
            {"unit_path": r"C:\r\zeta", "decision": "override",
             "override_artist": "X", "override_album": "Y"},
        ])
        assert applied == 0, (applied, msgs)
        assert len(msgs) == 4, msgs
        assert any("unbekannte Unit" in m for m in msgs), msgs
        assert any("nicht reviewbar" in m for m in msgs), msgs
        assert any("unbekannte Entscheidung" in m for m in msgs), msgs
        assert any("MBID" in m for m in msgs), msgs

        # 4) CSVs/Report wurden nach beiden Läufen geschrieben
        assert os.path.isfile(os.path.join(rd, "review.csv")), rd
        assert os.path.isfile(os.path.join(rd, "unidentified.csv")), rd
        assert os.path.isfile(os.path.join(rd, "import-report.md")), rd

    print("smoke_review_apply_rows: alle Assertionen grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
