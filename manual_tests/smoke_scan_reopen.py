# -*- coding: utf-8 -*-
"""Smoke test for re-decision on unit file-set changes (Story 11.4).

Run:  python manual_tests/smoke_scan_reopen.py
A decision (auto/asis/ignored/review/...) belongs to the file set the
scan saw at that time — NOT to the folder forever. Live case (11.2
Echtlauf): a fresh download landed in `Singles/Unknown`, a unit that
had been `ignored` via review on 2026-11-08; the scan merged the new
file into the unit but kept the status, so the file could never be
decided and rotted in staging. Checks: file-set change re-opens a
decided unit to `pending` (decision fields cleared), an unchanged file
set keeps the decision, pending units just refresh, and new units are
added as pending.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from musik import scan as S  # noqa: E402

WIN = os.name == "nt"


def nc(*paths: str) -> set[str]:
    return {os.path.normcase(os.path.normpath(p)) for p in paths}


def old_unit(status: str, files: list[str], **extra) -> dict:
    u = {"path": "/stg/unit", "files": files, "status": status,
         "reason": "decided earlier", "updated": 1000.0,
         "decision_kind": "single", "decision_type": "own-tags"}
    u.update(extra)
    return u


def new_unit(files: list[str]) -> dict:
    # faithful to scan.make_unit: it ALWAYS sets status ("pending"/"ignored")
    return {"path": "/stg/unit", "files": files, "n_files": len(files),
            "total_duration": 1.0, "kind": "album", "source": "scan",
            "singleton": True, "split_into_singletons": False, "hints": [],
            "artists_seen": [], "year_guess": None, "guessed": {},
            "unreadable_files": [], "meta_files": [], "status": "pending",
            "reason": ""}


def case1_unchanged_decision_kept():
    existing = {"k": old_unit("ignored", ["/stg/unit/a.m4a"])}
    outcome = S.merge_unit(existing, "k", new_unit(["/stg/unit/a.m4a"]))
    u = existing["k"]
    assert outcome == "kept", outcome
    assert u["status"] == "ignored", u["status"]
    assert u["decision_kind"] == "single", "decision fields survive"
    print("1) unchanged file set: ignored decision survives OK")


def case2_added_file_reopens():
    existing = {"k": old_unit("ignored", ["/stg/unit/a.m4a"])}
    outcome = S.merge_unit(existing, "k", new_unit(["/stg/unit/a.m4a",
                                                    "/stg/unit/b.m4a"]))
    u = existing["k"]
    assert outcome == "reopened", outcome
    assert u["status"] == "pending", u["status"]
    assert "changed" in u["reason"], u["reason"]
    for field in ("decision_kind", "decision_type", "file_results",
                  "chosen", "candidates", "guessed"):
        assert field not in u, f"{field} must be cleared"
    assert len(u["files"]) == 2, "refreshed facts kept"
    print("2) added file: decided unit re-opened to pending OK")


def case3_removed_file_reopens_auto():
    existing = {"k": old_unit("auto", ["/stg/unit/a.m4a", "/stg/unit/b.m4a"],
                              chosen={"id": "x"}, candidates=[])}
    outcome = S.merge_unit(existing, "k", new_unit(["/stg/unit/a.m4a"]))
    u = existing["k"]
    assert outcome == "reopened", outcome
    assert u["status"] == "pending", u["status"]
    assert "chosen" not in u
    print("3) removed file: auto unit re-opened (chosen cleared) OK")


def case4_pending_just_refreshes():
    existing = {"k": old_unit("pending", ["/stg/unit/a.m4a"])}
    outcome = S.merge_unit(existing, "k", new_unit(["/stg/unit/a.m4a",
                                                    "/stg/unit/b.m4a"]))
    u = existing["k"]
    assert outcome == "kept", outcome
    assert u["status"] == "pending", u["status"]
    assert len(u["files"]) == 2
    print("4) pending unit + new file: refresh only OK")


def case5_review_unchanged_kept():
    existing = {"k": old_unit("review", ["/stg/unit/a.m4a"])}
    outcome = S.merge_unit(existing, "k", new_unit(["/stg/unit/a.m4a"]))
    assert outcome == "kept"
    assert existing["k"]["status"] == "review"
    print("5) review unit, unchanged: stays review OK")


def case6_new_unit_added():
    existing: dict = {}
    outcome = S.merge_unit(existing, "k", new_unit(["/stg/unit/a.m4a"]))
    assert outcome == "added", outcome
    assert existing["k"]["status"] == "pending"
    print("6) new unit added as pending OK")


if __name__ == "__main__":
    case1_unchanged_decision_kept()
    case2_added_file_reopens()
    case3_removed_file_reopens_auto()
    case4_pending_just_refreshes()
    case5_review_unchanged_kept()
    case6_new_unit_added()
    print("smoke_scan_reopen: alle Assertionen grün")
