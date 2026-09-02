"""Import engine: turn scanned units into a tagged, organized library.

Real mode drives one beets ImportSession per unit (album or singleton),
deciding automatically where confidence is high and recording everything
else for review. Dry-run mode performs the exact same lookups and
decisions but never touches the database or files.
"""

import os
import time

from . import state as state_mod
from . import trash as trash_mod
from .paths import musik_config
from .scan import is_audio
from .session import (
    Decider,
    MusikSession,
    NetworkErrorRecorder,
    aggregate_unit_status,
)

netrec = NetworkErrorRecorder()

_BEETS_READY = False


def setup_beets() -> None:
    """Load beets config + plugins once per process."""
    global _BEETS_READY
    if _BEETS_READY:
        return
    from beets import plugins as beets_plugins

    netrec.install()
    beets_plugins.load_plugins()
    _BEETS_READY = True


def preflight() -> dict:
    """Check MusicBrainz reachability and the Discogs token.

    Returns {'musicbrainz': bool, 'discogs': bool, 'notes': [...]}.
    """
    setup_beets()
    from beets import plugins as beets_plugins

    out = {"musicbrainz": False, "discogs": False, "notes": []}

    import requests

    try:
        r = requests.get(
            "https://musicbrainz.org/ws/2/release",
            params={"query": "artist:ramones", "fmt": "json", "limit": 1},
            headers={"User-Agent": "musik/0.1 (beets-based tagger)"},
            timeout=15,
        )
        out["musicbrainz"] = r.status_code == 200
        if not out["musicbrainz"]:
            out["notes"].append(f"MusicBrainz answered HTTP {r.status_code}")
    except Exception as exc:
        out["notes"].append(f"MusicBrainz unreachable: {exc}")

    discogs = next(
        (
            p
            for p in beets_plugins.find_plugins()
            if getattr(p, "data_source", "").lower() == "discogs"
        ),
        None,
    )
    if discogs is None:
        out["notes"].append(
            "Discogs plugin not loaded (auth from discogs_token.json failed?)"
        )
    else:
        try:
            _ = discogs.discogs_client.search("ramones", type="release")[0]
            out["discogs"] = True
        except Exception as exc:
            out["notes"].append(f"Discogs token check failed: {exc}")

    return out


def build_decider(unit: dict | None = None, forced: dict | None = None) -> Decider:
    cfg = musik_config()
    forced = forced or {}
    return Decider(
        netrec,
        float(cfg["auto_accept_distance"]),
        int(cfg["review_candidates"]),
        forced_album_id=forced.get("album_id"),
        forced_track_id=forced.get("track_id"),
        override_artist=forced.get("artist"),
        override_album=forced.get("album"),
        unit=unit,
    )


def _item_paths(items) -> list[str]:
    return [os.fsdecode(i.path) for i in items]


def run_unit_dry(unit: dict, decider: Decider) -> dict:
    """Lookups + decisions only; nothing is written anywhere."""
    setup_beets()
    from beets.autotag import tag_album, tag_item
    from beets.importer.tasks import ImportTask, SingletonImportTask
    from beets.library import Item

    if unit.get("singleton") or unit.get("split_into_singletons"):
        results = []
        for f in unit["files"]:
            task = SingletonImportTask(None, Item.from_path(os.fsencode(f)))
            task.lookup_candidates([])
            action, record = decider.decide_item(task)
            record["paths"] = [f]
            record["action"] = action
            results.append(record)
    else:
        items = [Item.from_path(os.fsencode(f)) for f in unit["files"]]
        task = ImportTask(None, [os.fsencode(unit["import_path"])], items)
        task.lookup_candidates([])
        action, record = decider.decide_album(task)
        record["paths"] = [unit["import_path"]]
        record["action"] = action
        results = [record]

    status, reason = aggregate_unit_status(unit, results)
    return {"status": status, "reason": reason, "results": results}


def run_unit_real(lib, unit: dict, decider: Decider) -> dict:
    """Full pipeline for one unit: decide, apply, move, write, fetch art."""
    setup_beets()
    singletons = bool(unit.get("singleton") or unit.get("split_into_singletons"))
    session = MusikSession(lib, decider, [unit["import_path"]], singletons)
    try:
        session.run()
    finally:
        pass

    # New files that lost a duplicate comparison go to _trash.
    if session.duplicate_losers:
        detail = f"lost duplicate comparison ({unit['path']})"
        trash_mod.trash_files(session.duplicate_losers, "duplicate", detail)
        trash_mod.prune_empty_dirs(session.duplicate_losers, unit["import_path"])

    # Unmapped local tracks (extra files vs the matched release) are
    # archived so the library stays complete and auditable.
    if session.extra_files:
        detail = f"unmapped track, matched release for {unit['path']}"
        present = [f for f in session.extra_files if os.path.isfile(f)]
        trash_mod.trash_files(present, "unmapped-track", detail)
        trash_mod.prune_empty_dirs(present, unit["import_path"])

    status, reason = aggregate_unit_status(unit, session.results)
    outcome = {"status": status, "reason": reason, "results": session.results}
    if session.extra_files:
        outcome["unmapped_files"] = list(session.extra_files)
    return outcome


def _merge_result(unit: dict, outcome: dict) -> None:
    unit["status"] = outcome["status"]
    unit["reason"] = outcome.get("reason", "")
    unit["updated"] = time.time()
    if outcome.get("unmapped_files"):
        unit["unmapped_files"] = outcome["unmapped_files"]
    if unit.get("singleton") or unit.get("split_into_singletons"):
        unit["file_results"] = [
            {
                k: r.get(k)
                for k in ("paths", "status", "reason", "chosen", "candidates", "guessed")
            }
            for r in outcome.get("results", [])
        ]
    else:
        r = outcome.get("results", [{}])[0]
        unit["chosen"] = r.get("chosen")
        unit["candidates"] = r.get("candidates")
        unit["guessed"] = r.get("guessed")
        unit["reason"] = r.get("reason", "")


def _select(state: dict, statuses: list[str] | None, limit: int | None,
            only: str | None) -> list[dict]:
    sel = []
    want = os.path.normcase(os.path.normpath(only)) if only else None
    for u in state_mod.units(state).values():
        if want:
            upath = os.path.normcase(os.path.normpath(u["path"]))
            ipath = os.path.normcase(
                os.path.normpath(u.get("import_path") or u["path"])
            )
            # Exact unit match, or any unit underneath a given folder.
            if want not in (upath, ipath) and not upath.startswith(
                want + os.sep
            ):
                continue
        if statuses and u.get("status") not in statuses:
            continue
        sel.append(u)
    sel.sort(key=lambda u: u["path"])
    if limit:
        sel = sel[:limit]
    return sel


def _unit_label(u: dict) -> str:
    chosen = u.get("chosen") or {}
    if chosen.get("artist") or chosen.get("album"):
        return f"{chosen.get('artist', '?')} - {chosen.get('album') or chosen.get('track_title', '?')}"
    return os.path.basename(u["import_path"])


def cmd_import(dry_run: bool = False, statuses: list[str] | None = None,
               limit: int | None = None, only: str | None = None,
               rounds: int | None = None, quiet: bool = False) -> int:
    setup_beets()
    cfg = musik_config()
    rounds = rounds if rounds is not None else int(cfg["retry_rounds"])
    cooldown = float(cfg["retry_cooldown_seconds"])

    st = state_mod.load()
    selected = _select(st, statuses or ["pending"], limit, only)
    if not selected:
        print("nothing to import for the given filters")
        return 0

    pf = preflight()
    print(
        f"preflight: musicbrainz={'ok' if pf['musicbrainz'] else 'FAIL'}"
        f" discogs={'ok' if pf['discogs'] else 'FAIL'}"
    )
    for n in pf["notes"]:
        print("  note:", n)
    if dry_run:
        print(f"DRY RUN: {len(selected)} units (no files or DB touched)")

    lib = None
    if not dry_run:
        from beets import config as beets_config
        from beets.library import Library

        lib = Library(
            beets_config["library"].as_filename(),
            beets_config["directory"].as_filename(),
        )

    done = 0
    for i, unit in enumerate(selected, 1):
        if unit.get("status") in ("auto", "duplicate", "ignored"):
            continue
        netrec.clear()
        decider = build_decider(unit)
        label = _unit_label(unit)
        try:
            if dry_run:
                outcome = run_unit_dry(unit, decider)
                # Dry run: record previews to state without final statuses.
                unit["dryrun"] = {
                    "status": outcome["status"],
                    "reason": outcome.get("reason", ""),
                }
                first = (outcome.get("results") or [{}])[0]
                unit["chosen"] = first.get("chosen")
                unit["candidates"] = first.get("candidates") or unit.get("candidates")
                state_mod.set_status(unit, unit.get("status", "pending"),
                                     f"dry-run: {outcome['status']}")
            else:
                outcome = run_unit_real(lib, unit, decider)
                _merge_result(unit, outcome)
                state_mod.set_status(unit, outcome["status"],
                                     outcome.get("reason", ""))
        except KeyboardInterrupt:
            state_mod.save(st)
            print("\ninterrupted — state saved; rerun the same command to resume")
            return 130
        except Exception as exc:
            state_mod.set_status(unit, "error", f"{type(exc).__name__}: {exc}")
            print(f"[{i}/{len(selected)}] ERROR  {unit['import_path']}: {exc}")

        state_mod.save(st)
        done += 1
        if not quiet:
            print(
                f"[{i}/{len(selected)}] {unit['status']:<10} {label}"
                + (f"  ({unit['reason'][:90]})" if unit.get("reason") and unit["status"] not in ("auto",) else "")
            )

    # Retry rounds for units whose lookups failed (rate limit / network).
    if not dry_run and rounds > 0:
        for attempt in range(1, rounds + 1):
            pending = [
                u for u in state_mod.units(st).values()
                if u.get("status") == "network"
            ]
            if not pending:
                break
            print(f"retry round {attempt}/{rounds}: {len(pending)} network-deferred units, cooling down {cooldown:.0f}s")
            time.sleep(cooldown)
            for unit in pending:
                netrec.clear()
                decider = build_decider(unit)
                try:
                    outcome = run_unit_real(lib, unit, decider)
                    _merge_result(unit, outcome)
                    state_mod.set_status(unit, outcome["status"],
                                         outcome.get("reason", ""))
                except Exception as exc:
                    state_mod.set_status(unit, "error", f"{type(exc).__name__}: {exc}")
                state_mod.save(st)
                print(f"  retry {unit['status']:<10} {_unit_label(unit)}")

    from . import review as review_mod
    from . import report as report_mod

    if dry_run:
        report_mod.write_dryrun_report(st)
    else:
        review_mod.write_review_csv(st)
        review_mod.write_unidentified_csv(st)
        report_mod.write_import_report(st)

    c = state_mod.counts(st)
    print("status counts:", ", ".join(f"{k}={v}" for k, v in sorted(c.items())))
    return 0


def cmd_retry(rounds: int | None = None, include_unmatched: bool = False) -> int:
    statuses = ["network"] + (["unmatched"] if include_unmatched else [])
    return cmd_import(statuses=statuses, rounds=rounds or 0)
