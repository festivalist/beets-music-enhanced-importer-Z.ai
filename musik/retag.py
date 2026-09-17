"""`musik retag`: revisit as-is imports once MusicBrainz knows them (v1 report).

As-is units were filed from their own tags because no source matched at
import time. MusicBrainz keeps growing, so this command re-runs the album
lookup for those albums and reports which ones now have a STRONG match —
i.e. would be auto-accepted today.

v1 is strictly report-only (reports/retag-report.md). The apply step
(move files out of the library, re-import, swap DB rows) is deliberately
not implemented yet — it is the one operation that can mangle a healthy
library, so it stays in SCOPE §8 until explicitly requested.
"""

import os
import time
from collections import defaultdict

from .paths import reports_dir


def _asis_albums(lib) -> list[list]:
    """Group as-is-imported items (no MB track id, no data_source) by dir."""
    groups: dict[str, list] = defaultdict(list)
    for it in lib.items():
        if it.mb_trackid:
            continue
        if it.get("data_source"):
            continue
        groups[os.path.dirname(os.fsdecode(it.path))].append(it)
    out = []
    for d, items in groups.items():
        items.sort(key=lambda i: i.track or 0)
        out.append(items)
    out.sort(key=lambda items: items[0].albumartist or "")
    return out


def cmd_retag(limit: int | None = None, max_distance: float = 0.10) -> int:
    from .engine import setup_beets

    setup_beets()
    from beets import config as beets_config
    from beets.library import Library
    from beets.autotag import tag_album

    lib = Library(
        beets_config["library"].as_filename(),
        beets_config["directory"].as_filename(),
    )
    albums = _asis_albums(lib)
    if limit:
        albums = albums[:limit]
    if not albums:
        print("retag: no as-is albums found — nothing to do")
        return 0
    print(f"retag: looking up {len(albums)} as-is album(s) "
          "(network lookups, ~1/s — be patient)")

    strong: list[str] = []
    weak: list[str] = []
    none: list[str] = []
    for i, items in enumerate(albums, 1):
        own_artist = items[0].albumartist or items[0].artist or "?"
        own_album = items[0].album or "?"
        own_year = items[0].year or 0
        dirname = os.path.dirname(os.fsdecode(items[0].path))
        try:
            _artist, _album, proposal = tag_album(items, dirname)
        except Exception as e:
            none.append(f"`{own_artist} - {own_album}` — lookup failed: {e}")
            continue
        candidates = list(proposal.candidates)
        if not candidates:
            none.append(f"`{own_artist} - {own_album}` — no candidates")
            continue
        best = candidates[0]
        dist = float(best.distance)
        info = best.info
        label = (f"`{own_artist} - {own_album}` ({own_year or '?'}, "
                 f"{len(items)} tracks)  →  "
                 f"[{getattr(info, 'data_source', '?')}] "
                 f"{getattr(info, 'artist', '?')} - {getattr(info, 'album', '?')} "
                 f"({getattr(info, 'year', '?')})  distance {dist:.3f}")
        if dist <= max_distance:
            strong.append(label)
        else:
            weak.append(label)
        if i % 20 == 0:
            print(f"  ... {i}/{len(albums)} looked up "
                  f"({len(strong)} strong so far)")
        time.sleep(0.6)

    lines = [
        "# Retag report (as-is re-check)",
        "",
        f"Run: {time.strftime('%Y-%m-%d %H:%M:%S')}  |  "
        f"threshold: distance ≤ {max_distance}",
        "",
        f"Checked {len(albums)} as-is album(s): "
        f"**{len(strong)} strong** / {len(weak)} weak / {len(none)} without match.",
        "",
        "## Strong matches — would be auto-accepted today "
        f"({len(strong)})",
        "",
    ]
    lines += [f"- {s}" for s in strong] or ["(none)"]
    lines += ["", f"## Weak matches ({len(weak)})", ""]
    lines += [f"- {s}" for s in weak] or ["(none)"]
    lines += ["", f"## No usable match ({len(none)})", ""]
    lines += [f"- {s}" for s in none] or ["(none)"]
    lines += [
        "",
        "Apply step (re-file these albums via a real re-import) is not "
        "implemented yet — see SCOPE §8.",
    ]

    path = os.path.join(reports_dir(), "retag-report.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"\nretag: {len(strong)} strong / {len(weak)} weak / "
          f"{len(none)} without match")
    print("retag report:", path)
    return 0
