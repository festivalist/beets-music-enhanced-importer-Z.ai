"""Thin HTTP client for the local MusicGrabber instance (bot routing).

MusicGrabber (PI-SETUP Phase 9) is the second acquisition engine. The
Telegram bot sends free-text searches here first — multi-source search
with MusicBrainz duration checking and quality tiers — while Spotify/
YouTube links keep using the spotDL/SomeDL chain. When MusicGrabber cannot
deliver (unavailable, no results, failed job), the bot falls back to the
old chain. No auth headers: the instance deliberately runs no-login
(setting API_KEY locks the UI out — 2026-10-08 lesson) and the bot talks
to it on localhost.
"""

import re
import time

import requests

from .paths import musik_config

DEFAULTS = {
    "url": "http://127.0.0.1:38274",
    "enabled": True,
    "job_timeout": 600.0,  # single-track budget; playlists go via links
    # whole-album budget: one bulk import = N per-track jobs (~20 s/track
    # live-measured; 18 tracks took ~5.5 min)
    "album_job_timeout": 3600.0,
    # bot offers "whole album instead?" buttons after a free-text track
    "album_offer": True,
}
_API_TIMEOUT = (5, 30)  # (connect, read)


class MGUnavailable(Exception):
    """Container/network down or API error — caller should fall back."""


class MGNoResults(Exception):
    """Search returned nothing usable."""


class MGJobFailed(Exception):
    """Download job failed or did not finish in time."""


def mg_config() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(musik_config().get("musicgrabber") or {})
    return cfg


def _api(method: str, path: str, json_body: dict | None = None,
         timeout=None) -> dict:
    url = mg_config()["url"].rstrip("/") + path
    try:
        r = requests.request(method, url, json=json_body,
                             timeout=timeout or _API_TIMEOUT)
    except requests.RequestException as e:
        raise MGUnavailable(str(e)[:120]) from e
    if r.status_code >= 400:
        body = (r.text or "").strip()[:150]
        raise MGUnavailable(f"HTTP {r.status_code}" + (f": {body}" if body else ""))
    try:
        return r.json()
    except ValueError as e:
        raise MGUnavailable(f"non-JSON response from {path}") from e


def available() -> bool:
    try:
        _api("GET", "/api/settings", timeout=(3, 8))
        return True
    except MGUnavailable:
        return False


def _dur_secs(text) -> int | None:
    m = re.match(r"^(\d+):(\d{1,2})$", (text or "").strip())
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t}


def search(query: str, limit: int = 10) -> tuple[str, list[dict]]:
    """Returns (search_token, normalized results) in MG's own ranking.
    The search_token enables MusicGrabber's completeness check when the
    chosen result is passed to download()."""
    d = _api("POST", "/api/search",
             {"query": query, "limit": limit, "source": "all"},
             timeout=(5, 60))
    out = []
    for r in d.get("results") or []:
        artist = r.get("artist") or r.get("channel") or ""
        title = r.get("title") or ""
        # YouTube titles often repeat the channel ("The Fratellis - The
        # Fratellis - Chelsea Dagger") — strip a matching artist prefix.
        if artist and title.lower().startswith(artist.lower() + " - "):
            title = title[len(artist) + 3:].strip() or title
        out.append({
            "video_id": r.get("video_id"),
            "title": title,
            "artist": artist,
            "source": r.get("source") or "",
            # jiosaavn downloads REQUIRE the direct source_url (live-probed
            # 2026-10-08: POST /api/download answers 400 without it)
            "source_url": r.get("source_url") or "",
            "quality": r.get("quality") or "",
            "quality_tier": r.get("quality_tier") or 0,
            "relevance": r.get("relevance_score") or 0,
            "duration_secs": _dur_secs(r.get("duration")),
            "is_playlist": bool(r.get("is_playlist")),
        })
    return d.get("search_token") or "", out


# Titles of karaoke/tribute releases name the ORIGINAL artist — a
# title-based guard cannot tell them apart (live case: "Paris Music -
# Chelsea Dagger (Originally Performed By The Fratellis) [Full Vocal
# Version]", 320 kbps AAC, ranked above the official video).
_COVER_TITLE_RE = re.compile(
    r"originally performed|performed by|tribute|karaoke|in the style of|"
    r"made famous|cover version|\bcover\b|instrumental version|full vocal version",
    re.I,
)


def pick_result(query: str, results: list[dict]) -> dict | None:
    """Pick the result to download. Rank 1 alone is not trustworthy: MG
    sometimes puts a high-quality cover/namesake above the real recording.
    Prefer results whose ARTIST/CHANNEL carries the query's artist tokens
    (never the title — covers name the original artist there) and drop
    cover-style titles outright; among those, keep MG's own ranking
    (relevance, quality tier). Global rule, no per-artist special cases;
    users searching a bare title get rank 1 among non-cover results.
    """
    results = [
        r for r in results
        if r["video_id"] and not r["is_playlist"]
        and not _COVER_TITLE_RE.search(r["title"])
    ]
    if not results:
        return None
    artist_part = query.split(" - ")[0] if " - " in query else query
    want = _tokens(artist_part)
    if want:
        matching = [r for r in results if want <= _tokens(r["artist"])]
        if matching:
            results = matching
    return max(results, key=lambda r: (r["relevance"], r["quality_tier"]))


def download(result: dict, search_token: str = ""):
    """Queue a single-track download; returns the MusicGrabber job id
    (a string in current MG builds — live-probed 2026-10-08)."""
    body = {
        "video_id": result["video_id"],
        "title": result["title"],
        "source": result["source"],
        "download_type": "single",
    }
    if result.get("source_url"):
        body["source_url"] = result["source_url"]
    if search_token:
        body["search_token"] = search_token
    if result.get("duration_secs"):
        body["selected_duration_secs"] = result["duration_secs"]
    d = _api("POST", "/api/download", body, timeout=(5, 60))
    for key in ("id", "job_id"):
        v = d.get(key)
        if v:
            return v
    raise MGJobFailed(f"download response without job id: {str(d)[:120]}")


def wait_for_job(job_id, timeout: float | None = None,
                 progress=None) -> dict:
    """Poll the job until it completes; returns the final job dict.
    `progress(stage, job)` fires on stage changes (rate-limited by the
    caller). Raises MGJobFailed on failed/error status or timeout."""
    deadline = time.monotonic() + (timeout or float(mg_config()["job_timeout"]))
    while True:
        job = _api("GET", f"/api/jobs/{job_id}")
        if progress:
            progress(job.get("progress_stage"), job)
        status = (job.get("status") or "").lower()
        if status == "completed":
            return job
        if status in ("failed", "error", "cancelled", "canceled"):
            raise MGJobFailed((job.get("error") or status)[:200])
        if time.monotonic() >= deadline:
            raise MGJobFailed(
                f"job {job_id} not finished within "
                f"{int(timeout or mg_config()['job_timeout'])}s (status: {status})")
        time.sleep(5)


def resolve_release_group(release_group_mbid: str) -> dict:
    """Release-group MBID → representative release, exactly what
    download_album wants: {artist, album_title, release_mbid, year,
    track_count}. MG picks the pressing (its own release-choice rules),
    so the bot never has to. Raises MGUnavailable on HTTP errors."""
    return _api("POST", "/api/albums/resolve-release-group",
                {"release_group_mbid": release_group_mbid},
                timeout=(5, 60))


def download_album(artist: str, album_title: str, release_mbid: str) -> dict:
    """Queue a full-album download: MG fetches the MusicBrainz tracklist and
    runs a per-track bulk import into the staging tree
    Albums/<Artist>/<Album>/ (.albuminfo sidecar, gap-aware — tracks already
    in ITS staging dir are not re-queued). Returns the creation payload
    ({import_id, track_count, queued_count, existing_count, ...})."""
    d = _api("POST", "/api/albums/download",
             {"artist": artist, "album_title": album_title,
              "release_mbid": release_mbid},
             timeout=(5, 120))
    if not d.get("import_id"):
        raise MGJobFailed(f"album download without import_id: {str(d)[:120]}")
    return d


def import_status(import_id) -> dict:
    """One-shot bulk-import status snapshot (for /status live progress)."""
    return _api("GET", f"/api/bulk-import/{import_id}/status",
                timeout=(5, 30))


def wait_for_import(import_id, timeout: float | None = None,
                    progress=None) -> dict:
    """Poll the bulk import until every track job has settled; returns the
    final status dict ({status, total_tracks, searched, completed, failed,
    tracks[], complete, ...}). `progress(status)` fires per poll (caller
    rate-limits its own messages). A completed import with failed tracks is
    a PARTIAL SUCCESS — returned, not raised; the caller reports the gaps.
    Raises MGJobFailed only on import error/cancelled or timeout."""
    deadline = time.monotonic() + (timeout or float(mg_config()["album_job_timeout"]))
    while True:
        d = _api("GET", f"/api/bulk-import/{import_id}/status",
                 timeout=(5, 30))
        if progress:
            progress(d)
        if d.get("complete"):
            return d
        status = (d.get("status") or "").lower()
        if status in ("error", "cancelled", "canceled"):
            raise MGJobFailed((d.get("error") or status)[:200])
        if time.monotonic() >= deadline:
            raise MGJobFailed(
                f"album import {import_id} not finished within "
                f"{int(timeout or mg_config()['album_job_timeout'])}s "
                f"(status: {status})")
        time.sleep(10)
