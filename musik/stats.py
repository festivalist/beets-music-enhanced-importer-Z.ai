"""Library statistics (`musik stats`): the collection at a glance.

Console output plus reports/library-stats.md: totals, formats, decades,
top artists, monthly additions and the genre spread.
"""

import os
import time
from datetime import datetime
from collections import Counter

from .paths import reports_dir


def _open_library():
    from .engine import setup_beets

    setup_beets()
    from beets import config as beets_config
    from beets.library import Library

    return Library(
        beets_config["library"].as_filename(),
        beets_config["directory"].as_filename(),
    )


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    return f"{d}d {h}h {m}m" if d else f"{h}h {m}m"


def cmd_stats() -> int:
    lib = _open_library()
    items = list(lib.items())
    albums = list(lib.albums())

    total_secs = sum(i.length or 0 for i in items)
    total_bytes = 0
    formats: Counter = Counter()
    decades: Counter = Counter()
    artists: Counter = Counter()
    genres: Counter = Counter()
    added_months: Counter = Counter()
    for i in items:
        total_bytes += i.filesize or 0
        formats[i.format or "?"] += 1
        year = i.year or 0
        if year:
            decades[f"{year // 10 * 10}s"] += 1
        artists[(i.albumartist or "?").strip()] += 1
        for g in (i.genres or []):
            g = (g or "").strip()
            if g:
                genres[g] += 1
        added = getattr(i, "added", None)
        if isinstance(added, (int, float)):
            added = datetime.fromtimestamp(added)
        if added:
            added_months[added.strftime("%Y-%m")] += 1

    lines = [
        "# Library stats",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Totals",
        "",
        f"- **{len(items)}** tracks on **{len(albums)}** albums",
        f"- **{len(set(artists))}** album artists",
        f"- total duration: **{_fmt_duration(total_secs)}**",
        f"- total size: **{total_bytes / (1024 ** 3):.1f} GB**",
        "",
        "## Formats",
        "",
        "| format | tracks |",
        "|---|---|",
    ]
    for fmt, n in formats.most_common():
        lines.append(f"| {fmt} | {n} |")

    lines += ["", "## Decades", "", "```"]
    for dec in sorted(decades):
        bar = "#" * max(1, round(decades[dec] / max(decades.values()) * 40))
        lines.append(f"{dec:6} {decades[dec]:5}  {bar}")
    lines.append("```")

    lines += [
        "", "## Top 20 artists (by tracks)", "",
        "| artist | tracks |", "|---|---|",
    ]
    for artist, n in artists.most_common(20):
        lines.append(f"| {artist} | {n} |")

    lines += ["", "## Genres (top 15)", "", "| genre | tracks |", "|---|---|"]
    for g, n in genres.most_common(15):
        lines.append(f"| {g} | {n} |")

    lines += ["", "## Additions per month", "", "```"]
    for month in sorted(added_months):
        lines.append(f"{month}  {added_months[month]:4}  "
                     + "#" * max(1, round(added_months[month] / max(added_months.values()) * 40)))
    lines.append("```")

    path = os.path.join(reports_dir(), "library-stats.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    # console summary
    print(f"library: {len(items)} tracks / {len(albums)} albums / "
          f"{len(set(artists))} artists")
    print(f"duration: {_fmt_duration(total_secs)}   "
          f"size: {total_bytes / (1024 ** 3):.1f} GB")
    print("formats:", ", ".join(f"{k} {v}" for k, v in formats.most_common()))
    top = ", ".join(f"{a} ({n})" for a, n in artists.most_common(5))
    print(f"top artists: {top}")
    print("stats report:", path)
    return 0
