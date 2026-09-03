"""`musik review`: interactive decisions for hard-doubt units, right after
an import run. Mirrors beets' usual options per unit:

  [A] accept best candidate   [2]/[3] accept candidate 2/3
  [O] override search         [I] apply a MusicBrainz/Discogs ID
  [W] import as-is (own tags) [S] skip (stay in review)
  [X] ignore forever          [Q] abort remaining
"""

import os

from . import state as state_mod


def _show(unit: dict) -> None:
    g = unit.get("guessed") or {}
    print("=" * 70)
    print(os.path.basename(unit["import_path"]))
    print(
        f"  {unit.get('n_files', '?')} files | guess: "
        f"{g.get('artist', '?')} - {g.get('album', '?')}"
    )
    if unit.get("reason"):
        print(f"  why here: {unit['reason'][:150]}")
    cands = unit.get("candidates") or []
    if unit.get("singleton") or unit.get("split_into_singletons"):
        print("  (singleton unit — choose S, W, X or Q)")
    for i, c in enumerate(cands[:3], 1):
        print(
            f"  [{i}] {c.get('source', '?')}: {c.get('artist', '?')} - "
            f"{c.get('album', '?')} ({c.get('year', '?')}) "
            f"distance {c.get('distance')}"
        )
    if not cands:
        print("  (no candidates recorded)")


def _ask_choice(unit: dict) -> str:
    print(
        "\n[A] accept best   [2]/[3] candidate 2/3   [O] override search   "
        "[I] by MBID"
    )
    print("[W] import as-is   [S] skip   [X] ignore forever   "
          "[Q] abort remaining")
    try:
        return input("choice: ").strip().lower()
    except EOFError:
        return "q"


def _cand_id(unit: dict, n: int) -> str:
    cands = unit.get("candidates") or []
    if len(cands) >= n:
        return cands[n - 1].get("id", "") or ""
    return ""


def _run_forced(lib, unit: dict, forced: dict) -> str:
    """Run the unit with forced decisions; returns the new status."""
    from . import engine
    from . import state as state_mod

    engine.netrec.clear()
    decider = engine.build_decider(unit, forced=forced)
    outcome = engine.run_unit_real(lib, unit, decider)
    engine._merge_result(unit, outcome)
    state_mod.set_status(unit, outcome["status"], outcome.get("reason", ""))
    return outcome["status"]


def cmd_review(only: str | None = None) -> int:
    from . import engine
    from . import report as report_mod
    from . import review as review_mod
    from . import state as state_mod
    from .paths import reports_dir

    engine.setup_beets()
    st = state_mod.load()
    want = os.path.normcase(os.path.normpath(only)) if only else None

    selected = []
    for u in state_mod.units(st).values():
        if u.get("status") != "review":
            continue
        if want:
            upath = os.path.normcase(os.path.normpath(u["path"]))
            if want != upath and not upath.startswith(want + os.sep):
                continue
        selected.append(u)
    selected.sort(key=lambda u: u["path"])

    if not selected:
        print("review: nothing queued")
        return 0
    print(f"review: {len(selected)} unit(s) need a decision"
          " — Q aborts and leaves the rest for later")

    from beets import config as beets_config
    from beets.library import Library

    lib = Library(
        beets_config["library"].as_filename(),
        beets_config["directory"].as_filename(),
    )

    done = aborted = 0
    for idx, unit in enumerate(selected, 1):
        if unit.get("status") != "review":
            continue  # may have been decided as a side effect
        remaining = len(selected) - idx + 1
        print(f"\n--- [{idx}/{len(selected)}] ({remaining} after this) ---")
        _show(unit)

        while True:
            choice = _ask_choice(unit)

            if choice == "q":
                print("aborting — remaining units stay in review")
                aborted = remaining
                break

            if choice == "s":
                print("  skipped (stays in review.csv)")
                break

            if choice == "x":
                state_mod.set_status(unit, "ignored", "ignored via interactive review")
                state_mod.save(st)
                print("  ignored forever")
                done += 1
                break

            if choice == "w":
                from . import asis

                ok, why = asis.tags_complete(unit)
                if not ok:
                    print(f"  cannot import as-is: {why}")
                    continue
                asis.cmd_asis(only=unit["path"])
                # cmd_asis loads state from disk (fresh dicts); sync the
                # decision back into our in-memory copy.
                st2 = state_mod.load()
                fresh = state_mod.get_unit(st2, unit["path"])
                if fresh and fresh.get("status") == "asis":
                    unit.update(fresh)
                    state_mod.put_unit(st, unit)
                    state_mod.save(st)
                    done += 1
                    break
                print("  as-is import did not complete — pick again or S to leave it")
                continue

            if choice in ("a", "1", "2", "3"):
                n = 1 if choice in ("a", "1") else int(choice)
                cid = _cand_id(unit, n)
                if not cid:
                    print(f"  no candidate {n} recorded")
                    continue
                status = _run_forced(lib, unit, {
                    "album_id": cid, "track_id": cid,
                })
            elif choice == "o":
                try:
                    artist = input("  artist (empty = keep guess): ").strip()
                    album = input("  album  (empty = keep guess): ").strip()
                except EOFError:
                    print("aborting")
                    aborted = remaining
                    break
                g = unit.get("guessed") or {}
                forced = {
                    "artist": artist or g.get("artist") or None,
                    "album": album or g.get("album") or None,
                }
                forced = {k: v for k, v in forced.items() if v}
                if not forced:
                    print("  nothing entered")
                    continue
                status = _run_forced(lib, unit, forced)
            elif choice == "i":
                try:
                    mbid = input(
                        "  release/track MBID or URL: "
                    ).strip()
                except EOFError:
                    print("aborting")
                    aborted = remaining
                    break
                if not mbid:
                    print("  nothing entered")
                    continue
                status = _run_forced(lib, unit, {
                    "album_id": mbid, "track_id": mbid,
                })
            else:
                print("  ? — A / 2 / 3 / O / I / W / S / X / Q")
                continue

            state_mod.save(st)
            chosen = unit.get("chosen") or {}
            if status in ("auto", "asis"):
                print(f"  imported: {chosen.get('artist', '?')} - "
                      f"{chosen.get('album') or chosen.get('track_title', '?')}")
                done += 1
                break
            print(f"  not imported (status {status}: {unit.get('reason', '')[:140]})")
            print("  pick again or S to leave it")
        if aborted:
            break

    review_mod.write_review_csv(st)
    review_mod.write_unidentified_csv(st)
    report_mod.write_import_report(st)
    print(f"\nreview done: {done} decided, {aborted or 0} aborted; "
          f"queue updated in {os.path.join(reports_dir(), 'review.csv')}")
    return 0
