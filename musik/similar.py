"""Similar-artist recommendations (`musik similar`).

Asks the ListenBrainz similarity dataset (which works on MusicBrainz IDs,
no API key needed) for artists similar to the library's artists, then
aggregates the ones NOT already in the library into a "worth acquiring"
report: reports/similar-artists.md.

Results are cached per artist in state.json; re-runs only query artists
not seen yet (or everything with --refresh).
"""

import re
import time
import uuid

import requests

from . import state as state_mod
from .paths import reports_dir

# Labs endpoint; `algorithm` must be one of its fixed enum values. This is
# the standard session-based similarity model.
LB_URL = "https://labs.api.listenbrainz.org/similar-artists/json"
LB_ALGORITHM = (
    "session_based_days_7500_session_300_contribution_3_threshold_10"
    "_limit_100_filter_True_skip_30"
)
BATCH = 50          # artist MBIDs per request
SLEEP_SECS = 1.2    # between requests, keeps us polite
VA_RE = re.compile(r"^\s*(various artists|various|v\.?a\.)\s*$", re.I)
VA_MBID = "33a1ec2f-79fa-4217-a804-42ed641053c2"  # MusicBrainz' Various Artists
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _library_artists(lib) -> tuple[dict[str, str], set[str]]:
    """(mbid -> name) for valid single artists, plus normalized name set."""
    by_mbid: dict[str, str] = {}
    names: set[str] = set()
    for it in lib.items():
        for name in (it.albumartist or "", it.artist or ""):
            if name and not VA_RE.match(name):
                names.add(_norm_name(name))
        aid = (it.mb_artistid or "").strip()
        # multi-artist rows join ids with ';'; only clean single UUIDs are
        # usable for the API (beatport4 stores plain numeric ids there)
        first = aid.split(";")[0].strip()
        if (UUID_RE.match(first) and first != VA_MBID
                and not VA_RE.match(it.artist or "")):
            by_mbid.setdefault(first, (it.artist or "?").strip())
    return by_mbid, names


def _get_batch(params: list[tuple]) -> requests.Response | None:
    for attempt in range(3):
        try:
            return requests.get(LB_URL, params=params, timeout=40)
        except requests.RequestException as e:
            print(f"  network hiccup ({e.__class__.__name__}), retrying...")
            time.sleep(3 * (attempt + 1))
    return None


def _fetch_similar(mbids: list[str]) -> dict[str, list[dict]]:
    """Query the labs API; returns reference_mbid -> entries.

    The endpoint wants REPEATED artist_mbids params. A batch with one bad
    MBID comes back 400, so failures are bisected down to singles and bad
    ids are dropped.
    """
    params = [("algorithm", LB_ALGORITHM)] + [("artist_mbids", m) for m in mbids]
    r = _get_batch(params)
    if r is None:
        return {}
    if r.status_code == 400 and len(mbids) > 1:
        out: dict[str, list[dict]] = {}
        mid = len(mbids) // 2
        for part in (mbids[:mid], mbids[mid:]):
            time.sleep(SLEEP_SECS)
            for k, v in _fetch_similar(part).items():
                out[k] = v
        return out
    if r.status_code != 200:
        print(f"  batch dropped (HTTP {r.status_code})")
        return {}

    out = {mb: [] for mb in mbids}
    for row in r.json():
        ref = row.get("reference_mbid")
        if ref in out:
            out[ref].append(row)
    return out


def cmd_similar(top: int = 30, refresh: bool = False) -> int:
    lib = _open_library()
    by_mbid, lib_names = _library_artists(lib)
    if not by_mbid:
        print("no artists with MusicBrainz IDs in the library — nothing to do")
        return 0

    st = state_mod.load()
    cache: dict = (st.setdefault("meta", {}).setdefault("similar_cache", {}))
    if refresh:
        cache.clear()

    todo = [mb for mb in by_mbid if mb not in cache]
    print(f"{len(by_mbid)} artists with MBIDs, {len(todo)} not yet queried")

    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        got = _fetch_similar(chunk)
        for mb, entries in got.items():
            cache[mb] = [
                {"mbid": e.get("artist_mbid"), "name": e.get("name", ""),
                 "score": int(e.get("score") or 0)}
                for e in entries if e.get("artist_mbid")
            ]
        st.setdefault("meta", {})["similar_last_run"] = time.time()
        state_mod.save(st)  # save per chunk: a crash keeps prior work
        print(f"  queried {min(i + BATCH, len(todo))}/{len(todo)} artists")
        time.sleep(SLEEP_SECS)

    # aggregate recommendations not already in the library
    agg: dict[str, dict] = {}
    for ref_mb, entries in cache.items():
        ref_name = by_mbid.get(ref_mb, ref_mb)
        for e in entries:
            mb, name = e["mbid"], e["name"]
            if mb in by_mbid or _norm_name(name) in lib_names:
                continue  # already in the library
            a = agg.setdefault(mb, {"name": name, "score": 0, "refs": []})
            a["score"] += e["score"]
            a["refs"].append(ref_name)

    ranked = sorted(agg.items(), key=lambda kv: kv[1]["score"], reverse=True)

    lines = [
        "# Similar artists worth acquiring",
        "",
        f"Based on {len(cache)} library artists via the ListenBrainz "
        "similarity dataset. 'Missing' = not present in this library.",
        "",
        f"## Top {top} suggestions", "",
        "| # | artist | score | recommended by (your artists) |",
        "|---|---|---|---|",
    ]
    for rank, (mb, a) in enumerate(ranked[:top], 1):
        refs = ", ".join(sorted(set(a["refs"]))[:4])
        more = f" +{len(set(a['refs'])) - 4}" if len(set(a["refs"])) > 4 else ""
        lines.append(f"| {rank} | [{a['name']}](https://musicbrainz.org/artist/{mb}) "
                     f"| {a['score']} | {refs}{more} |")

    lines += ["", "## Runner-ups (next 40)", ""]
    for mb, a in ranked[top:top + 40]:
        lines.append(f"- [{a['name']}](https://musicbrainz.org/artist/{mb}) "
                     f"— score {a['score']}, {len(set(a['refs']))} of your artists")

    path = _report_path()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"\ntop suggestions:")
    for mb, a in ranked[:10]:
        print(f"  {a['name']:40} score {a['score']:6}  "
              f"({len(set(a['refs']))} of your artists)")
    print("similar report:", path)
    return 0


def _report_path() -> str:
    import os

    return os.path.join(reports_dir(), "similar-artists.md")


def _open_library():
    from .engine import setup_beets

    setup_beets()
    from beets import config as beets_config
    from beets.library import Library

    return Library(
        beets_config["library"].as_filename(),
        beets_config["directory"].as_filename(),
    )
