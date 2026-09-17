"""New-release monitoring (`musik releases`).

Browses MusicBrainz for release groups (albums/EPs) of the library's
artists that appeared since the last run — a lightweight "what's new"
report without any download ambitions: reports/new-releases.md.

State holds the timestamp of the last successful run (default lookback:
90 days on first run). MusicBrainz is browsed at 1 request/second.
"""

import os
import time
from datetime import datetime, timedelta, timezone

import requests

from . import state as state_mod
from .paths import reports_dir

BROWSE_URL = "https://musicbrainz.org/ws/2/release-group"
HEADERS = {"User-Agent": "musik/2.0 ( https://github.com/festivalist )"}
# release groups of these primary types are interesting for a collection
# (the browse API wants lowercase primary types)
WANTED_TYPES = {"album", "ep"}
STATE_KEY = "releases_last_check"


def _artist_mbids(lib) -> dict[str, str]:
    """mbid -> name for single, valid-MBID artists (see similar.py)."""
    import re
    import uuid as _uuid

    from .similar import VA_RE

    by_mbid: dict[str, str] = {}
    for it in lib.items():
        aid = (it.mb_artistid or "").strip().split(";")[0].strip()
        name = (it.artist or "").strip()
        if re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            aid, re.I,
        ) and name and not VA_RE.match(name):
            by_mbid.setdefault(aid, name)
    return by_mbid


def _parse_since(since: str | None, state: dict) -> datetime:
    if since:
        return datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    last = (state.get("meta") or {}).get(STATE_KEY)
    if last:
        return datetime.fromtimestamp(last, tz=timezone.utc)
    return datetime.now(tz=timezone.utc) - timedelta(days=90)


def cmd_releases(since: str | None = None) -> int:
    from .engine import setup_beets

    setup_beets()
    from beets import config as beets_config
    from beets.library import Library

    lib = Library(
        beets_config["library"].as_filename(),
        beets_config["directory"].as_filename(),
    )
    artists = _artist_mbids(lib)
    if not artists:
        print("no artists with MusicBrainz IDs in the library — nothing to do")
        return 0

    st = state_mod.load()
    start = _parse_since(since, st)
    start_str = start.strftime("%Y-%m-%d")
    print(f"checking {len(artists)} artists for releases since {start_str} "
          "(~1 request/second)")

    new_groups: list[dict] = []
    checked = 0
    for mbid, name in sorted(artists.items()):
        params = {
            "artist": mbid,
            "type": "|".join(sorted(WANTED_TYPES)),
            "status": "Official",
            "fmt": "json",
        }
        try:
            r = requests.get(BROWSE_URL, params=params, headers=HEADERS, timeout=30)
        except requests.RequestException as e:
            print(f"  {name}: network error ({e.__class__.__name__}) — "
                  "stopping early; timestamp NOT advanced, re-run resumes")
            break
        if r.status_code == 400 and "type" in r.text:
            # some artists produce odd type unions; retry bare
            params.pop("type")
            r = requests.get(BROWSE_URL, params=params, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"  {name}: HTTP {r.status_code} — skipped")
            checked += 1
            time.sleep(1)
            continue
        for rg in r.json().get("release-groups", []):
            first = rg.get("first-release-date") or ""
            if not first or first < start_str:
                continue
            new_groups.append({
                "artist": name,
                "title": rg.get("title", "?"),
                "date": first,
                "type": rg.get("primary-type", "?"),
                "mbid": rg.get("id", ""),
            })
        checked += 1
        if checked % 25 == 0:
            print(f"  ... {checked}/{len(artists)} artists checked, "
                  f"{len(new_groups)} new release groups")
        time.sleep(1.05)  # musicbrainz ratelimit: 1/s

    if checked == len(artists):
        st.setdefault("meta", {})[STATE_KEY] = time.time()
        state_mod.save(st)

    new_groups.sort(key=lambda g: (g["date"], g["artist"]), reverse=True)

    lines = [
        "# New releases of your library artists",
        "",
        f"Window: {start_str} → today. "
        f"{len(new_groups)} release group(s) across {len(artists)} artists.",
        "",
        "| date | artist | release | type | link |",
        "|---|---|---|---|---|",
    ]
    for g in new_groups:
        link = (f"[MB](https://musicbrainz.org/release-group/{g['mbid']})"
                if g["mbid"] else "-")
        lines.append(f"| {g['date']} | {g['artist']} | {g['title']} "
                     f"| {g['type']} | {link} |")
    if not new_groups:
        lines.append("| - | (nothing new) | | | |")

    path = os.path.join(reports_dir(), "new-releases.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"\n{len(new_groups)} new release group(s) found")
    for g in new_groups[:10]:
        print(f"  {g['date']}  {g['artist']} — {g['title']}")
    print("releases report:", path)
    return 0
