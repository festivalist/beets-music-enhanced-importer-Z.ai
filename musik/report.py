"""Human-readable reports: scan, dry-run, import results and session totals."""

import os
import time
from collections import Counter

from . import state as state_mod
from .paths import reports_dir


def _status_counts(state: dict) -> Counter:
    return Counter(u.get("status", "pending") for u in state_mod.units(state).values())


def _fmt_dur(seconds: float | None) -> str:
    if not seconds:
        return "-"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def write_scan_report(state: dict, notes: list[str]) -> str:
    path = os.path.join(reports_dir(), "scan-report.md")
    units = list(state_mod.units(state).values())
    units.sort(key=lambda u: u["path"])
    c = _status_counts(state)
    meta = state.get("meta", {}).get("last_scan", {})

    lines = [
        "# Scan report",
        "",
        f"Root: `{meta.get('root', '?')}`",
        "",
        "## Status counts",
        "",
        "| status | units |",
        "|---|---|",
    ]
    for k, v in sorted(c.items()):
        lines.append(f"| {k} | {v} |")
    lines += ["", "## Units", "", "| status | files | duration | kind | hints | path |", "|---|---|---|---|---|---|"]
    for u in units:
        lines.append(
            "| {status} | {n} | {dur} | {kind} | {hints} | `{p}` |".format(
                status=u.get("status", "pending"),
                n=u.get("n_files", "?"),
                dur=_fmt_dur(u.get("total_duration")),
                kind=u.get("kind", "?"),
                hints=", ".join(u.get("hints", [])) or "-",
                p=u["path"],
            )
        )
    if meta.get("junk_count"):
        lines += ["", f"Non-audio files recorded (left in place): {meta['junk_count']}"]
    if notes:
        lines += ["", "## Notes", ""]
        lines += [f"- {n}" for n in notes]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def write_dryrun_report(state: dict) -> str:
    path = os.path.join(reports_dir(), "dry-run-report.md")
    units = [
        u for u in state_mod.units(state).values() if u.get("dryrun")
    ]
    units.sort(key=lambda u: u["path"])
    preview = Counter(u["dryrun"]["status"] for u in units)

    lines = [
        "# Dry-run report (nothing was moved or written)",
        "",
        "What the import *would* do right now:",
        "",
        "| would-be status | units |",
        "|---|---|",
    ]
    for k, v in sorted(preview.items()):
        lines.append(f"| {k} | {v} |")
    lines += ["", "## Per unit", ""]
    for u in units:
        d = u["dryrun"]
        chosen = u.get("chosen") or {}
        label = (
            f"{chosen.get('artist', '?')} - {chosen.get('album') or chosen.get('track_title', '?')}"
            if chosen else "-"
        )
        lines.append(
            f"### {os.path.basename(u['import_path'])} — would be **{d['status']}**"
        )
        lines.append(f"- path: `{u['path']}`")
        lines.append(f"- {u.get('n_files', '?')} files, {_fmt_dur(u.get('total_duration'))}")
        lines.append(f"- best candidate: {label}")
        if d.get("reason"):
            lines.append(f"- reason: {d['reason']}")
        cands = u.get("candidates") or []
        for i, c in enumerate(cands[:3], 1):
            lines.append(
                f"- candidate {i}: {c.get('source', '?')}: {c.get('artist', '?')} - {c.get('album', '?')} "
                f"(distance {c.get('distance')})"
            )
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def write_import_report(state: dict) -> str:
    path = os.path.join(reports_dir(), "import-report.md")
    units = list(state_mod.units(state).values())
    c = _status_counts(state)

    lines = [
        "# Import report",
        "",
        "## Status counts",
        "",
        "| status | units |",
        "|---|---|",
    ]
    for k, v in sorted(c.items()):
        lines.append(f"| {k} | {v} |")
    total_files = sum(u.get("n_files", 0) for u in units)
    lines += ["", f"Total units: {len(units)}, total audio files: {total_files}", ""]

    def section(title: str, statuses: list[str], detail: bool = True) -> None:
        sel = sorted(
            (u for u in units if u.get("status") in statuses), key=lambda u: u["path"]
        )
        lines.append(f"## {title} ({len(sel)})")
        lines.append("")
        if not sel:
            lines.append("(none)")
            lines.append("")
            return
        if detail:
            for u in sel:
                reason = (u.get("reason") or "").replace("\n", " ")[:200]
                lines.append(f"- `{u['path']}` — {reason}")
                proto = (u.get("protocol") or {}).get("summary")
                if proto:
                    lines.append(f"  - protocol: {proto}")
        else:
            for u in sel:
                lines.append(f"- `{u['path']}`")
        lines.append("")

    section("Imported automatically", ["auto"])
    section("Imported as-is (own tags)", ["asis"])
    section("Waiting in review.csv", ["review"])
    section("Unmatched (left in place)", ["unmatched"])
    section("Deferred: lookup failed (retry with `musik retry`)", ["network"])
    section("Duplicates (losers moved to _trash)", ["duplicate"], detail=False)
    section("Errors", ["error"])
    section("Ignored by decision", ["ignored"], detail=False)

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


KIND_ORDER = ["album", "ep", "single", "compilation", "mix"]
TYPE_ORDER = ["direct", "enhanced", "own-tags", "undecided",
              "deferred", "duplicate", "failed"]


def aggregate_session(units: dict, since: float) -> tuple[dict, dict]:
    """Aggregate the units touched since `since` into a session summary.

    Returns (rows, stats): rows maps release kind -> {decision type: n},
    stats holds file totals and the undecided unit list.
    """
    rows: dict[str, dict[str, int]] = {}
    stats = {"files_imported": 0, "files_unmapped": 0, "undecided": []}
    for u in units.values():
        if (u.get("updated") or 0) < since:
            continue
        if u.get("status") in ("pending", "ignored"):
            continue
        kind = u.get("decision_kind") or "album"
        dt = u.get("decision_type") or "undecided"
        rows.setdefault(kind, {}).setdefault(dt, 0)
        rows[kind][dt] += 1
        if u.get("status") in ("auto", "asis"):
            stats["files_imported"] += u.get("n_files", 0)
            stats["files_unmapped"] += len(u.get("unmapped_files") or [])
        if dt == "undecided":
            stats["undecided"].append(os.path.basename(u["import_path"]))
    return rows, stats


def cmd_session_begin() -> int:
    st = state_mod.load()
    start = time.time()
    st.setdefault("meta", {})["session_start"] = start
    state_mod.save(st)
    print("session started", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start)))
    return 0


def cmd_summary() -> int:
    st = state_mod.load()
    since = (st.get("meta") or {}).get("session_start")
    if not since:
        print("no session started — run `musik session-begin` first "
              "(import-here.bat does this automatically)")
        return 1
    rows, stats = aggregate_session(state_mod.units(st), since)

    header = ["kind"] + TYPE_ORDER + ["total"]
    widths = [max(6, len(h)) for h in header]
    body = []
    kinds = [k for k in KIND_ORDER if k in rows] + \
            sorted(k for k in rows if k not in KIND_ORDER)
    for kind in kinds:
        counts = rows[kind]
        line = [kind] + [str(counts.get(t, 0)) for t in TYPE_ORDER]
        line.append(str(sum(counts.values())))
        body.append(line)

    def fmt(sep: str) -> list[str]:
        out = []
        for line in [header] + body:
            out.append(sep.join(c.ljust(w) for c, w in zip(line, widths)).rstrip())
        return out

    console = fmt("  ")
    print("session summary (since",
          time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(since)), ")")
    for line in console:
        print(" ", line)
    print(
        f"  files imported: {stats['files_imported']}, "
        f"unmapped archived: {stats['files_unmapped']}"
    )
    if stats["undecided"]:
        print("  still undecided:")
        for n in stats["undecided"]:
            print(f"    - {n}")

    md = ["# Session report", "",
          f"Since {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(since))}",
          "", "| " + " | ".join(header) + " |",
          "|---|" + "---|" * len(header)]
    for line in body:
        md.append("| " + " | ".join(line) + " |")
    md += ["", f"Files imported: {stats['files_imported']}  |  "
               f"Unmapped archived: {stats['files_unmapped']}"]
    if stats["undecided"]:
        md += ["", "## Still undecided", ""]
        md += [f"- {n}" for n in stats["undecided"]]
    path = os.path.join(reports_dir(), "session-report.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    print("session report:", path)
    return 0


def verify(state: dict) -> dict:
    """Library sanity checks against the beets DB."""
    from .engine import setup_beets

    setup_beets()
    from beets import config as beets_config
    from beets.library import Library

    lib = Library(
        beets_config["library"].as_filename(),
        beets_config["directory"].as_filename(),
    )
    out = {
        "albums": 0,
        "items": 0,
        "albums_missing_art": 0,
        "albums_missing_genre": 0,
        "items_missing_path": 0,
    }
    albums = list(lib.albums())
    out["albums"] = len(albums)
    out["items"] = len(list(lib.items()))
    for a in albums:
        if not a.artpath or not os.path.isfile(os.fsdecode(a.artpath)):
            out["albums_missing_art"] += 1
        if not getattr(a, "genres", None):
            out["albums_missing_genre"] += 1
    for item in lib.items():
        if not os.path.isfile(os.fsdecode(item.path)):
            out["items_missing_path"] += 1
    return out
