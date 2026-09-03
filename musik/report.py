"""Human-readable reports: scan, dry-run and import results."""

import os
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
