"""New-release monitoring (`musik releases`).

Browses MusicBrainz for release groups (albums/EPs) of the library's
artists that appeared since the last run — a lightweight "what's new"
report without any download ambitions: reports/new-releases.md.

State holds the timestamp of the last successful run (default lookback:
90 days on first run). MusicBrainz is browsed at 1 request/second.
"""

import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from . import state as state_mod
from .paths import reports_dir

BROWSE_URL = "https://musicbrainz.org/ws/2/release-group"
SEARCH_URL = "https://musicbrainz.org/ws/2/recording"
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
            for attempt in range(2):  # MB 503 hiccups are transient
                if r.status_code < 500:
                    break
                time.sleep(5 * (attempt + 1))
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


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t}


# dropped from the "whole album instead?" offer: VA compilations and live
# albums are never the canonical home of a studio track
_UNWANTED_SECONDARY = {"compilation", "live"}


def _recording_release_groups(recordings: list[dict], want: set[str],
                              limit: int) -> list[dict]:
    """Pure ranking: MB recording-search results → album/EP release-group
    candidates. Artist-token guard (covers name the original artist in the
    TITLE, never in their own credit), official releases only, dedup by
    release-group, earliest date per group. Top `limit` by search score with
    the NEWEST group always included — user rule 2026-10-09: with more
    candidates than buttons, the newest release must still be offered."""
    best: dict[str, dict] = {}
    for rec in recordings:
        credit = rec.get("artist-credit") or []
        artist = credit[0].get("name", "") if credit and isinstance(credit[0], dict) else ""
        if want and not want <= _tokens(artist):
            continue
        score = rec.get("score") or 0
        for rel in rec.get("releases") or []:
            if rel.get("status") not in (None, "Official"):
                continue
            rg = rel.get("release-group") or {}
            if (rg.get("primary-type") or "").lower() not in WANTED_TYPES:
                continue
            secondary = {s.lower() for s in rg.get("secondary-types") or []}
            if secondary & _UNWANTED_SECONDARY:
                continue
            mbid = rg.get("id") or ""
            if not mbid:
                continue
            date = rg.get("first-release-date") or rel.get("date") or ""
            year = date[:4] if date[:4].isdigit() else ""
            cand = best.get(mbid)
            if cand is None:
                best[mbid] = {
                    "rg_mbid": mbid,
                    "artist": artist,
                    "title": rg.get("title") or rel.get("title") or "?",
                    "type": (rg.get("primary-type") or "?").lower(),
                    "year": year,
                    "score": score,
                }
            else:
                cand["score"] = max(cand["score"], score)
                if year and (not cand["year"] or year < cand["year"]):
                    cand["year"] = year
    ranked = sorted(best.values(), key=lambda c: c["score"], reverse=True)[:limit]
    if len(best) > limit:
        newest = max(best.values(), key=lambda c: c["year"] or "0000")
        if not any(c["rg_mbid"] == newest["rg_mbid"] for c in ranked):
            ranked[-1] = newest
    return ranked


def _detransliterate(text: str) -> str:
    """ASCII → German umlauts/ß. MusicBrainz's Lucene search does not fold
    transliterations (live 2026-10-09: artist:"Grauzone" AND recording:
    "Eisbaer" → 0 hits, "Eisbär" → exact match), so the bot retries with the
    de-transliterated spelling when the strict query found nothing."""
    return (text.replace("ae", "ä").replace("oe", "ö")
                .replace("ue", "ü").replace("ss", "ß"))


def _mb_recording_search(artist: str, title: str) -> list[dict]:
    """Recording search with transient-503 retry and (only on zero results)
    a de-transliterated second pass. Returns raw recordings or []."""
    variants = [(artist, title)]
    detrans = (_detransliterate(artist), _detransliterate(title))
    if detrans != (artist, title):
        variants.append(detrans)
    for v_artist, v_title in variants:
        parts = []
        if v_artist.strip():
            parts.append(f'artist:"{v_artist.strip()}"')
        parts.append(f'recording:"{v_title.strip()}"')
        for attempt in range(2):  # MB 503 hiccups are transient
            try:
                r = requests.get(SEARCH_URL,
                                 params={"query": " AND ".join(parts),
                                         "limit": 25, "fmt": "json"},
                                 headers=HEADERS, timeout=30)
            except requests.RequestException as e:
                print(f"releases: recording search failed "
                      f"({e.__class__.__name__}) — no album offer")
                return []
            if r.status_code == 200:
                recordings = r.json().get("recordings") or []
                if recordings:
                    return recordings
                break  # zero results → try the next spelling variant
            if r.status_code < 500:
                print(f"releases: recording search HTTP {r.status_code} — "
                      "no album offer")
                return []
            time.sleep(3)
        time.sleep(1.05)  # musicbrainz ratelimit: 1/s
    return []


def track_album_candidates(artist: str, title: str, library=None,
                           limit: int = 3) -> list[dict]:
    """Album/EP release groups containing the requested track — the bot's
    "whole album instead?" offer after a free-text track request. Returns
    [{rg_mbid, artist, title, type, year, score, in_library?}] or [] (MB
    unreachable/unmatched — the offer is optional and must never break the
    track job). in_library marks groups already in beets via
    mb_releasegroupid; those buttons mean gap-fill, not a fresh copy."""
    recordings = _mb_recording_search(artist, title)
    cands = _recording_release_groups(recordings, _tokens(artist), limit)
    if library is not None:
        for c in cands:
            try:
                c["in_library"] = next(
                    library.albums(f"mb_releasegroupid:{c['rg_mbid']}"),
                    None) is not None
            except Exception:
                c["in_library"] = False
    return cands
