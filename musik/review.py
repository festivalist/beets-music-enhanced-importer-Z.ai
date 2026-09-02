"""Review queue: review.csv (user decisions) and unidentified.csv.

review.csv is generated from every unit with status `review`. The user
fills in the `decision` column (accept / accept2 / override / unmatched /
ignore) and optional override columns, then `musik apply` processes the
edited file in batch.
"""

import csv
import os

from . import state as state_mod

REVIEW_COLUMNS = [
    "unit_path",
    "status",
    "guessed_artist",
    "guessed_album",
    "n_files",
    "cand1_source", "cand1_artist", "cand1_album", "cand1_year", "cand1_distance", "cand1_id",
    "cand2_artist", "cand2_album", "cand2_distance", "cand2_id",
    "cand3_artist", "cand3_album", "cand3_distance", "cand3_id",
    "decision",          # accept | accept2 | override | unmatched | ignore
    "override_artist",
    "override_album",
    "override_mbid",
    "notes",
]

UNMATCHED_COLUMNS = [
    "unit_path", "status", "reason", "n_files", "guessed_artist", "guessed_album",
]


def _review_row(unit: dict) -> dict:
    cands = unit.get("candidates") or []
    guessed = unit.get("guessed") or {}
    row = {
        "unit_path": unit["path"],
        "status": unit.get("status", ""),
        "guessed_artist": guessed.get("artist", ""),
        "guessed_album": guessed.get("album", ""),
        "n_files": unit.get("n_files", ""),
        "decision": "",
        "override_artist": "",
        "override_album": "",
        "override_mbid": "",
        "notes": unit.get("reason", "")[:200],
    }
    for idx, c in enumerate(cands[:3], 1):
        row[f"cand{idx}_source"] = c.get("source", "")
        row[f"cand{idx}_artist"] = c.get("artist", "")
        row[f"cand{idx}_album"] = c.get("album", "")
        row[f"cand{idx}_year"] = c.get("year", "")
        row[f"cand{idx}_distance"] = c.get("distance", "")
        row[f"cand{idx}_id"] = c.get("id", "")
    return row


def write_review_csv(state: dict) -> str:
    from .paths import reports_dir

    path = os.path.join(reports_dir(), "review.csv")
    units_with_review = [
        u for u in state_mod.units(state).values() if u.get("status") == "review"
    ]
    units_with_review.sort(key=lambda u: u["path"])
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS)
        w.writeheader()
        for u in units_with_review:
            w.writerow({k: _review_row(u).get(k, "") for k in REVIEW_COLUMNS})
    return path


def write_unidentified_csv(state: dict) -> str:
    from .paths import reports_dir

    path = os.path.join(reports_dir(), "unidentified.csv")
    rows = [
        u for u in state_mod.units(state).values()
        if u.get("status") in ("unmatched", "network", "error")
    ]
    rows.sort(key=lambda u: (u.get("status"), u["path"]))
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(UNMATCHED_COLUMNS)
        for u in rows:
            w.writerow([
                u["path"], u.get("status", ""), (u.get("reason") or "")[:300],
                u.get("n_files", ""), (u.get("guessed") or {}).get("artist", ""),
                (u.get("guessed") or {}).get("album", ""),
            ])
    return path


def read_decisions(csv_path: str) -> list[dict]:
    out = []
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            decision = (row.get("decision") or "").strip().lower()
            if not decision:
                continue
            out.append({
                "unit_path": row.get("unit_path", ""),
                "decision": decision,
                "override_artist": (row.get("override_artist") or "").strip(),
                "override_album": (row.get("override_album") or "").strip(),
                "override_mbid": (row.get("override_mbid") or "").strip(),
                "notes": (row.get("notes") or "").strip(),
            })
    return out


def apply_decisions(csv_path: str | None = None) -> int:
    """Process an edited review.csv: re-import accepted/overridden units."""
    from . import engine
    from .paths import reports_dir

    csv_path = csv_path or os.path.join(reports_dir(), "review.csv")
    if not os.path.isfile(csv_path):
        print(f"no review csv at {csv_path}")
        return 1

    decisions = read_decisions(csv_path)
    if not decisions:
        print("review.csv contains no decisions")
        return 0

    st = state_mod.load()
    applied = 0
    for d in decisions:
        unit = state_mod.get_unit(st, d["unit_path"])
        if unit is None:
            print(f"  unknown unit (skipped): {d['unit_path']}")
            continue
        if unit.get("status") not in ("review", "unmatched", "network"):
            print(f"  not reviewable, current status {unit.get('status')}: {d['unit_path']}")
            continue

        if d["decision"] == "ignore":
            state_mod.set_status(unit, "ignored", d["notes"] or "ignored via review")
            state_mod.save(st)
            applied += 1
            continue
        if d["decision"] == "unmatched":
            state_mod.set_status(unit, "unmatched", "confirmed unmatched via review")
            state_mod.save(st)
            applied += 1
            continue

        forced = {}
        if d["decision"] == "accept":
            forced["album_id"] = _cand_id(unit, 1)
            forced["track_id"] = _cand_id(unit, 1)
        elif d["decision"] == "accept2":
            forced["album_id"] = _cand_id(unit, 2)
            forced["track_id"] = _cand_id(unit, 2)
        elif d["decision"] == "override":
            if d["override_mbid"]:
                forced["album_id"] = d["override_mbid"]
                forced["track_id"] = d["override_mbid"]
            if d["override_artist"]:
                forced["artist"] = d["override_artist"]
            if d["override_album"]:
                forced["album"] = d["override_album"]
            if not forced:
                print(f"  override without fields (skipped): {d['unit_path']}")
                continue
        else:
            print(f"  unknown decision '{d['decision']}' (skipped): {d['unit_path']}")
            continue

        engine.setup_beets()
        from beets import config as beets_config
        from beets.library import Library

        lib = Library(
            beets_config["library"].as_filename(),
            beets_config["directory"].as_filename(),
        )
        decider = engine.build_decider(unit, forced=forced)
        engine.netrec.clear()
        try:
            outcome = engine.run_unit_real(lib, unit, decider)
            engine._merge_result(unit, outcome)
            state_mod.set_status(unit, outcome["status"], outcome.get("reason", ""))
            print(f"  applied [{unit['status']}] {os.path.basename(unit['import_path'])}")
        except Exception as exc:
            state_mod.set_status(unit, "error", f"{type(exc).__name__}: {exc}")
            print(f"  ERROR applying {d['unit_path']}: {exc}")
        state_mod.save(st)
        applied += 1

    # Refresh the CSVs and report afterwards.
    write_review_csv(st)
    write_unidentified_csv(st)
    from . import report as report_mod

    report_mod.write_import_report(st)
    print(f"processed {applied} decision(s)")
    return 0


def _cand_id(unit: dict, n: int) -> str:
    cands = unit.get("candidates") or []
    if len(cands) >= n:
        return cands[n - 1].get("id", "") or ""
    return ""
