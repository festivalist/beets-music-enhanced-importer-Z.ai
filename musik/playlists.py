"""Plex-Playlists aus Fetch-Jobs (`musik fetch` / musik bot).

A downloaded playlist ends up track-by-track in its real album folders —
which is right for the library, but loses the playlist itself. This module
rebuilds it: order and title come from spotDL's `--m3u` sidecar (written
into the job dir before beets moves anything), the final library paths come
from diffing the beets DB around the import chain, and the result is a
plain .m3u with absolute library paths. `musik/plex.py` uploads that file
to the Plex server, which turns it into a normal playlist (visible in
Plexamp like any other).

SomeDL (YouTube) has no m3u support: entries fall back to the job's audio
files in alphabetical order, the playlist is named after the job.

State: one JSON per job under <state_dir>/playlists/, so a later `/asis`
of parked review tracks can fill the missing entries and re-upload.
"""

import difflib
import json
import os
import re
import time

from . import state as state_mod
from .paths import (
    bootstrap,
    incoming_dir,
    library_root,
    musik_config,
    state_dir,
)

EXTINF_RE = re.compile(r"^#EXTINF:\s*(-?\d+)\s*,\s*(.*?)\s*$", re.I)


# --------------------------------------------------------------------------
# entry collection (runs BEFORE the import chain: staging files still exist)
# --------------------------------------------------------------------------

def is_playlist_query(query: str) -> bool:
    """Playlist links only — album/track/artist links should not spawn a
    second copy of an album as a Plex playlist."""
    q = (query or "").lower()
    if "open.spotify.com" in q or "spotify.link" in q:
        return "/playlist/" in q or "/playlist?" in q
    if any(h in q for h in ("youtube.com", "youtu.be")):
        return "list=" in q
    return False


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _parse_sidecar(path: str) -> list[dict]:
    """Entries from an m3u/m3u8: [{file, artist, title}] in file order.

    spotDL writes `#EXTINF:<dur>,<album-artist> - <title>` followed by the
    file path; plain playlists without EXTINF fall back to parsing the
    basename ('{artists} - {title}.m4a').
    """
    entries: list[dict] = []
    pending_meta: tuple[str, str] | None = None
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                m = EXTINF_RE.match(line)
                if m:
                    meta = m.group(2)
                    if " - " in meta:
                        artist, title = meta.split(" - ", 1)
                        pending_meta = (artist.strip(), title.strip())
                    else:
                        pending_meta = ("", meta.strip())
                    continue
                if line.startswith("#"):
                    continue
                base = os.path.basename(
                    line.replace("\\", "/").rstrip("/"))
                if not base:
                    continue
                artist, title = pending_meta or ("", "")
                if not title and " - " in os.path.splitext(base)[0]:
                    b_artist, b_title = os.path.splitext(base)[0].split(" - ", 1)
                    artist, title = artist or b_artist, b_title
                entries.append({
                    "file": base, "artist": artist, "title": title,
                })
                pending_meta = None
    except OSError:
        return []
    return entries


def _tag_entries(files: list[str]) -> list[dict]:
    """Fallback entries from the staging files' own tags, PRESERVING the
    given order (callers pass download/playlist order). SomeDL jobs tag
    from MusicBrainz, so these are good match keys."""
    from .scan import tag_of

    entries = []
    for f in files:
        try:
            artist = tag_of(f, "albumartist") or tag_of(f, "artist") or ""
            title = tag_of(f, "title") or ""
        except Exception:
            artist, title = "", ""
        entries.append({
            "file": os.path.basename(f),
            "artist": str(artist), "title": str(title),
        })
    return entries


def _ytdlp_fetch(url: str, cookies: str | None) -> dict | None:
    """Flat playlist metadata via yt-dlp (bundled with spotDL). Network
    part, isolated for testability; None on any failure."""
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        return None
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "noplaylist": False, "extract_flat": True,
    }
    if cookies and os.path.isfile(cookies):
        opts["cookiefile"] = cookies
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"playlists: yt-dlp konnte die Playlist nicht lesen "
              f"({str(e)[:120]}) — Reihenfolge-Fallback")
        return None
    return info if info and info.get("_type") == "playlist" else None


def _order_from_info(info: dict, files: list[str],
                     tags: dict[str, dict] | None = None) -> tuple[str, list[dict]] | None:
    """(playlist name, entries in true playlist order) from flat yt-dlp
    info. Files are matched to entries by video title — SomeDL names
    files after the video title and retags via MusicBrainz, so basename
    and title tag both work as match keys. Unmatched entries are skipped
    (undownloadable videos), leftover files are appended at the end."""
    yt_entries = [e for e in (info.get("entries") or [])
                  if e and (e.get("title") or "").strip()]
    if not yt_entries:
        return None
    tags = tags if tags is not None else {
        t["file"]: t for t in _tag_entries(files)}
    used: set[str] = set()
    ordered: list[dict] = []

    def find(yt_title: str, mode: str) -> str | None:
        nt = _norm(yt_title)
        if not nt:
            return None
        for f in files:
            if f in used:
                continue
            if mode == "name":
                nb = _norm(os.path.splitext(os.path.basename(f))[0])
                if nb and nt == nb:
                    return f
            elif mode == "name-loose":
                nb = _norm(os.path.splitext(os.path.basename(f))[0])
                if nb and (nt in nb or nb in nt):
                    return f
            else:  # tag title (MusicBrainz-corrected)
                tt = _norm((tags.get(os.path.basename(f)) or {}).get("title", ""))
                if tt and (nt == tt or nt in tt or tt in nt):
                    return f
        return None

    for ye in yt_entries:
        f = (find(ye["title"], "name") or find(ye["title"], "name-loose")
             or find(ye["title"], "tag"))
        if f is None:
            continue
        used.add(f)
        te = tags.get(os.path.basename(f)) or {}
        ordered.append({
            "file": os.path.basename(f),
            "artist": (te.get("artist") or ye.get("channel") or ""),
            "title": (te.get("title") or ye["title"]),
        })
    if not ordered:
        return None
    for f in files:  # leftovers: failed matches, retry latecomers
        if f not in used:
            te = tags.get(os.path.basename(f)) or {}
            ordered.append({"file": os.path.basename(f),
                            "artist": te.get("artist", ""),
                            "title": te.get("title", "")})
    name = (info.get("title") or "").strip()
    return name, ordered


def _youtube_order(job) -> tuple[str, list[dict]] | None:
    """True playlist name + order for a YouTube job via yt-dlp (metadata
    only — the download itself stays with SomeDL)."""
    m = re.search(r"[?&]list=([\w-]+)", job.query)
    if not m:
        return None
    url = f"https://www.youtube.com/playlist?list={m.group(1)}"
    cookies = None
    try:
        from .fetch import cookie_path, fetch_config

        cookies = cookie_path(fetch_config())
    except Exception:
        pass
    info = _ytdlp_fetch(url, cookies)
    if info is None:
        return None
    return _order_from_info(info, job.files)


def _spotify_oembed_name(url: str) -> str | None:
    """Public playlist name via Spotify's oEmbed endpoint (no auth).
    Story 2.7: without spotDL's m3u sidecar the only name on hand is the
    job id slug ('spotify-37i9d…') — this resolves the real title before
    the upload. Name only, no track list."""
    try:
        import requests

        r = requests.get(
            "https://open.spotify.com/oembed",
            params={"url": url}, timeout=20,
        )
        if r.status_code != 200:
            return None
        title = ((r.json() or {}).get("title") or "").strip()
        return title or None
    except Exception as e:
        print(f"playlists: Spotify-oEmbed namenlos ({str(e)[:120]}) "
              f"— Job-Label-Fallback")
        return None


SPOTIFY_ID_NAME_RE = re.compile(r"^spotify-[A-Za-z0-9_-]{8,}$")


def _job_label(job_id: str) -> str:
    """Human-ish name from 'fetch-20260921-123001-spotify-bestsongs'."""
    parts = job_id.split("-", 3)
    return (parts[3] if len(parts) > 3 else job_id).strip("-")


def prepare_mg(pl_dir: str) -> tuple[str, dict] | None:
    """Story 2.2: specs for a MusicGrabber playlist staging dir
    (Playlists/<Name>/ with 'Artist - Title' files and optionally MG's
    own m3u). Name and order come from the m3u when MG's 'Create M3U'
    is on; without it the tags in alphabetical order are the best
    available guess. Returns (name, spec) or None when the dir holds no
    audio."""
    from .scan import is_audio

    try:
        names = sorted(os.listdir(pl_dir))
    except OSError:
        return None
    audio = [
        os.path.join(pl_dir, n) for n in names
        if os.path.isfile(os.path.join(pl_dir, n)) and is_audio(n)
    ]
    if not audio:
        return None
    name = os.path.basename(os.path.normpath(pl_dir)) or "MG Playlist"
    entries = None
    for n in names:
        if n.lower().endswith((".m3u", ".m3u8")):
            entries = _parse_sidecar(os.path.join(pl_dir, n))
            if entries:
                break
    if not entries:
        entries = _tag_entries(audio)
    return name, {"name": name, "entries": entries}


def prepare(job) -> list[dict] | None:
    """Collect playlist specs for a fetch job before the import runs.

    Returns [{name, entries:[...]}] or None when the query was no playlist
    (or nothing usable was found). Call build() with the same result after
    the import chain; both never raise — a playlist problem must not be
    able to fail an import.
    """
    try:
        if not job.files:
            return None
        specs: list[dict] = []
        for name in sorted(os.listdir(job.job_dir)):
            if name.lower().endswith((".m3u", ".m3u8")):
                entries = _parse_sidecar(os.path.join(job.job_dir, name))
                if entries:
                    specs.append({
                        "name": os.path.splitext(name)[0],
                        "entries": entries,
                    })
        if not specs and not is_playlist_query(job.query):
            # no sidecar and no playlist link: an album/track job must not
            # spawn a Plex playlist (a sidecar alone IS the evidence —
            # spotDL writes it only for playlist links; this also lets
            # pre-marker staging folders resume, Story 2.7)
            return None
        if specs:
            # spotDL writes the sidecar after the FIRST download run;
            # tracks that only succeeded in a retry round are missing from
            # it — append them (own tags) so they still reach the playlist
            mentioned = {e["file"] for s in specs for e in s["entries"]}
            extras = [f for f in job.files
                      if os.path.basename(f) not in mentioned]
            if extras:
                specs[-1]["entries"].extend(_tag_entries(extras))
        else:
            # No sidecar (SomeDL): YouTube jobs get the TRUE playlist name
            # and order from yt-dlp metadata; Spotify jobs resolve at least
            # the true NAME via oEmbed (Story 2.7 — the job id slug would
            # upload as 'spotify-37i9d…'); without that, mtime is the
            # best guess (paced downloads finish in playlist order).
            name = None
            entries = None
            if job.kind == "youtube":
                got = _youtube_order(job)
                if got:
                    name, entries = got
            elif job.kind == "spotify":
                name = _spotify_oembed_name(job.query)
            if entries is None:
                def _mtime(f: str) -> float:
                    try:
                        return os.path.getmtime(f)
                    except OSError:
                        return 0.0
                by_time = sorted(job.files, key=lambda f: (_mtime(f), f))
                entries = _tag_entries(by_time)
            specs = [{
                "name": name or _job_label(job.job_id),
                "entries": entries,
            }]
        return specs
    except Exception as e:
        print(f"playlists: prepare failed for {job.job_id}: "
              f"{type(e).__name__}: {e}")
        return None


# --------------------------------------------------------------------------
# item matching (new beets items vs. playlist entries)
# --------------------------------------------------------------------------

def _score(entry: dict, item: dict) -> int:
    """Similarity of a playlist entry to a library item (artist/title only —
    beets may have retagged, so 'Remastered 2011' suffixes must not kill a
    match)."""
    e_art = _norm(entry.get("artist"))
    e_tit = _norm(entry.get("title"))
    i_art = _norm(item.get("artist")) or _norm(item.get("albumartist"))
    i_tit = _norm(item.get("title"))
    if not e_tit or not i_tit:
        return 0
    score = 0
    if e_tit == i_tit:
        score += 3
    elif (len(e_tit) >= 6 and i_tit.startswith(e_tit)) or \
            (len(i_tit) >= 6 and e_tit.startswith(i_tit)):
        score += 2
    elif e_tit in i_tit or i_tit in e_tit:
        score += 1
    elif difflib.SequenceMatcher(None, e_tit, i_tit).ratio() >= 0.8:
        score += 1
    if score < 3:
        # Story 2.9: mid-title variants — the playlist source wrote extra
        # words INSIDE the title ('Winter (The Four Seasons) - Techno Mix'
        # vs the retagged '… (Extended Techno Mix)'). A long shared prefix
        # whose leftover tails are compatible (one ends with the other) is
        # the same recording (live match won 18.11.).
        pre = os.path.commonprefix([e_tit, i_tit])
        if len(pre) >= 12:
            e_tail, i_tail = e_tit[len(pre):], i_tit[len(pre):]
            if e_tail and i_tail and \
                    (e_tail.endswith(i_tail) or i_tail.endswith(e_tail)):
                score = 3
    if score < 3 and len(i_tit) >= 4 and \
            e_tit.startswith(i_tit) and e_tit[len(i_tit):].startswith("feat"):
        # Story 2.9: featuring credits — entry 'X (feat. Y)' vs the MB-
        # canonical item 'X' (live case 'Amor (feat. CERES)'). The core
        # title is identical, the rest is a credit, not another song.
        score = 3
    if not e_art or not i_art:
        return score
    if e_art == i_art:
        score += 2
    elif e_art in i_art or i_art in e_art or \
            difflib.SequenceMatcher(None, e_art, i_art).ratio() >= 0.8:
        score += 1
    return score


def _match_entries(entries: list[dict], items: list[dict]) -> None:
    """Fill entry['dest'] greedily in playlist order; each item is used at
    most once. Unmatched entries keep dest=None (still parked in review,
    failed download, ...)."""
    used: set[int] = set()
    for entry in entries:
        best_idx, best_score = -1, 0
        for i, item in enumerate(items):
            if i in used:
                continue
            s = _score(entry, item)
            if s > best_score:
                best_idx, best_score = i, s
        if best_idx >= 0 and best_score >= 3:
            entry["dest"] = items[best_idx]["path"]
            entry["item_id"] = items[best_idx]["id"]
            used.add(best_idx)
        else:
            entry["dest"] = None
            entry.pop("item_id", None)


# --------------------------------------------------------------------------
# beets access (id diff around the import chain)
# --------------------------------------------------------------------------

def _lib():
    from .engine import open_library

    return open_library()


def snapshot_ids() -> set[int] | None:
    """Item ids currently in the beets DB (None when beets is unusable)."""
    try:
        bootstrap()
        from .engine import setup_beets

        setup_beets()
        return {i.id for i in _lib().items()}
    except Exception as e:
        print(f"playlists: beets snapshot failed: {type(e).__name__}: {e}")
        return None


def _items_since(ids_before: set[int] | None) -> list[dict]:
    """Library items added after the snapshot: [{id, path, title, artist,
    albumartist}]. With ids_before=None the whole library is returned (used
    by rebuild to fill gaps after a later /asis). Items whose file is gone
    (stale rows with dead staging paths) never match: an m3u entry pointing
    at a missing file is worthless in Plex (KK-GOTCHA 16.11. — Titel-
    Fallback-Matches landeten auf toten Rows)."""
    lib = _lib()
    out = []
    for it in lib.items():
        if ids_before is not None and it.id in ids_before:
            continue
        path = os.fsdecode(it.path)
        if not os.path.isfile(path):
            continue
        out.append({
            "id": it.id,
            "path": path,
            "title": it.title or "",
            "artist": it.artist or "",
            "albumartist": it.albumartist or "",
        })
    return out


# --------------------------------------------------------------------------
# state + m3u files
# --------------------------------------------------------------------------

def _playlists_state_dir() -> str:
    d = os.path.join(state_dir(), "playlists")
    os.makedirs(d, exist_ok=True)
    return d


def m3u_dir() -> str:
    """Where the Plex-readable .m3u files live. Default: a _playlists folder
    inside the music library root (PMS is guaranteed to read there; the bot
    and PMS run on the same host)."""
    cfg = (musik_config().get("plex") or {})
    d = (cfg.get("playlist_dir") or "").strip() \
        or os.path.join(library_root(), "_playlists")
    os.makedirs(d, exist_ok=True)
    return d


def _safe_filename(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", (name or "").strip())
    s = re.sub(r"\s+", " ", s).strip(" .")
    return (s or "playlist")[:80]


def _state_path(pl_or_id) -> str:
    if isinstance(pl_or_id, dict):
        ident = pl_or_id.get("state_file") or pl_or_id["job_id"]
    else:
        ident = pl_or_id
    return os.path.join(_playlists_state_dir(), f"{ident}.json")


def _load_state(job_id: str) -> dict | None:
    p = _state_path(job_id)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None
    return None


def _save_state(pl: dict) -> None:
    pl["updated"] = time.time()
    p = _state_path(pl)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(pl, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, p)


def write_m3u(pl: dict, path: str | None = None) -> str:
    """(Re)write the .m3u for a playlist state; returns its path.

    An explicit path (or a path carried over from a previous state in
    build()) wins over the name-derived one: Plex replaces a playlist by
    m3u FILE path, so a rename must keep writing the same file — a new
    filename would spawn a second playlist instead (Story 2.7,
    'Umbenennung idempotent')."""
    path = path or pl.get("m3u") \
        or os.path.join(m3u_dir(), _safe_filename(pl["name"]) + ".m3u")
    lines = ["#EXTM3U"]
    for t in pl["tracks"]:
        if not t.get("dest"):
            continue
        lines.append(f"#EXTINF:-1,{t.get('artist', '')} - {t.get('title', '')}")
        lines.append(t["dest"])
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    pl["m3u"] = path
    return path


# --------------------------------------------------------------------------
# public API (used by fetch/bot/cli)
# --------------------------------------------------------------------------

def build(job, specs: list[dict] | None, ids_before: set[int] | None) -> list[dict]:
    """After the import chain: map entries to final paths, write state+m3u.
    Returns the playlist states (also stored on job.playlists)."""
    if not specs:
        return []
    states: list[dict] = []
    try:
        new_items = _items_since(ids_before) if ids_before is not None else []
        for spec in specs:
            # one job usually yields one playlist; several sidecars get
            # one state file each (plain job_id would overwrite)
            sf = job.job_id if len(specs) == 1 else (
                f"{job.job_id}--{_safe_filename(spec['name'])}")
            # keep earlier matches (item_id) stable across rebuilds; keep
            # the m3u file path stable even across RENAMES — Plex replaces
            # a playlist by file path, a new filename would spawn a second
            # playlist (Story 2.7, 'Umbenennung idempotent')
            prev = None
            prev_m3u = None
            old = _load_state(sf)
            if old:
                if old.get("name") == spec["name"]:
                    prev = {t["file"]: t for t in old.get("tracks", [])}
                prev_m3u = old.get("m3u")
            tracks = []
            for e in spec["entries"]:
                t = dict(e)
                if prev and prev.get(e["file"], {}).get("dest"):
                    t["dest"] = prev[e["file"]]["dest"]
                    t["item_id"] = prev[e["file"]].get("item_id")
                tracks.append(t)
            # 1) freshly imported items (exact-ish), 2) the rest of the
            # library — a playlist track that was discarded as a duplicate
            # of an existing copy should reference that copy
            _match_entries([t for t in tracks if not t.get("dest")],
                           new_items)
            _match_entries([t for t in tracks if not t.get("dest")],
                           _items_since(None))
            pl = {
                "job_id": job.job_id,
                "job_dir": job.job_dir,
                "state_file": sf,
                "name": spec["name"],
                "query": job.query,
                "created": time.time(),
                "tracks": tracks,
            }
            write_m3u(pl, prev_m3u)
            _save_state(pl)
            states.append(pl)
    except Exception as e:
        print(f"playlists: build failed for {job.job_id}: "
              f"{type(e).__name__}: {e}")
    return states


def summarize(pl: dict) -> str:
    total = len(pl.get("tracks", []))
    have = sum(1 for t in pl.get("tracks", []) if t.get("dest"))
    line = f"Playlist „{pl['name']}“: {have}/{total} Track(s) zugeordnet"
    if have < total:
        missing = [t.get("title") or t.get("file")
                   for t in pl.get("tracks", []) if not t.get("dest")]
        line += (" — fehlend: " + "; ".join(missing[:3])
                 + (" …" if len(missing) > 3 else ""))
    return line


def _resolve_upload_name(pl: dict) -> str | None:
    """True name for a state still carrying a 'spotify-<id>' label (old
    states built before the oEmbed fallback, or a leaked job-id slug).
    Story 2.7: resolve ONCE from the query, rename the state + m3u in
    place (same file path → Plex re-upload REPLACES, see write_m3u), so
    repeated uploads stay idempotent. None = nothing to fix."""
    name = pl.get("name") or ""
    if not SPOTIFY_ID_NAME_RE.match(name):
        return None
    if not (pl.get("query") or "").strip().lower().startswith(
            ("http://open.spotify.com", "https://open.spotify.com",
             "http://spotify.link", "https://spotify.link")):
        return None
    real = _spotify_oembed_name(pl["query"])
    if not real or real == name:
        return None
    pl["name"] = real
    if pl.get("m3u"):
        write_m3u(pl, pl["m3u"])
        _save_state(pl)
    return real


def upload(states: list[dict]) -> list[str]:
    """Upload playlist states to Plex (after a library refresh). Returns
    message lines; empty when Plex is not configured or nothing to do."""
    from . import plex as plex_mod

    msgs: list[str] = []
    for pl in states:
        if not pl.get("m3u"):
            continue
        title = pl.get("name")
        real = _resolve_upload_name(pl)
        if real:
            msgs.append(f"🎵 Playlist umbenannt: „{title}“ → „{real}“")
            title = real
        ok, note = plex_mod.upload_playlist(pl["m3u"], title=title)
        if ok:
            msgs.append(f"🎵 {note}")
            pl["plex"] = {"uploaded": time.time(), "message": note}
            _save_state(pl)
        elif note:  # configured but failed
            msgs.append(f"⚠️ {note}")
    return msgs


def state_for_job(job_id: str) -> list[dict]:
    """Playlist states belonging to one fetch job id (exact match or the
    multi-sidecar '<job_id>--<name>' variants). Used by the resume path
    (Story 2.7) to re-upload a playlist whose staging folder is gone."""
    job_id = (job_id or "").strip()
    if not job_id:
        return []
    out = []
    for pl in all_states():
        if pl.get("job_id") == job_id or \
                (pl.get("job_id") or "").startswith(f"{job_id}--"):
            out.append(pl)
    return out


def find_by_name(name: str) -> list[dict]:
    """Playlist states whose name (or m3u filename) matches, for the
    manual `musik plex --playlist` retry."""
    name_l = (name or "").strip().lower()
    out = []
    try:
        for f in sorted(os.listdir(_playlists_state_dir())):
            if not f.endswith(".json"):
                continue
            pl = _load_state(f[:-5])
            if pl and (pl.get("name", "").lower() == name_l or
                       _safe_filename(pl.get("name", "")).lower() == name_l):
                out.append(pl)
    except OSError:
        pass
    return out


def all_states() -> list[dict]:
    out = []
    try:
        for f in sorted(os.listdir(_playlists_state_dir())):
            if f.endswith(".json"):
                pl = _load_state(f[:-5])
                if pl:
                    out.append(pl)
    except OSError:
        pass
    return out


def rebuild(unit_paths: list[str]) -> list[dict]:
    """Re-resolve playlist entries whose tracks appeared later (typically a
    /asis import of parked review units). Returns the touched states; a
    state belongs to the job dir its unit paths live under."""
    roots = [state_mod.norm_key(p) for p in unit_paths if p]
    out: list[dict] = []
    try:
        for name in sorted(os.listdir(_playlists_state_dir())):
            if not name.endswith(".json"):
                continue
            pl = _load_state(name[:-5])
            if not pl:
                continue
            # unit paths live inside the job dir (old states carry only
            # the job id = basename under the incoming root)
            job_root = state_mod.norm_key(
                pl.get("job_dir")
                or os.path.join(incoming_dir(), pl.get("job_id", "")))
            if not any(state_mod.path_under(r, job_root)
                       for r in roots):
                continue
            if all(t.get("dest") for t in pl.get("tracks", [])):
                continue  # nothing to fill
            _match_entries(
                [t for t in pl["tracks"] if not t.get("dest")],
                _items_since(None),
            )
            write_m3u(pl)
            _save_state(pl)
            out.append(pl)
    except Exception as e:
        print(f"playlists: rebuild failed: {type(e).__name__}: {e}")
    return out


def repath() -> list[dict]:
    """Re-resolve playlist entries whose dest FILE vanished (Story 2.8):
    quality upgrades replace library files (singleton dedup 2.3/2.8,
    dedupe --apply, manual trash) and the old m3u paths age — entries
    keep artist/title, drop the dead dest and re-match against the
    library. Touched states get their m3u rewritten (same file path, so
    a Plex re-upload replaces). Returns the touched states; the caller
    uploads them after its Plex refresh. A track with no surviving
    library copy stays unmatched (m3u entry dropped until it returns)."""
    touched: list[dict] = []
    try:
        for pl in all_states():
            dead = [t for t in pl.get("tracks", [])
                    if t.get("dest") and not os.path.isfile(t["dest"])]
            if not dead:
                continue
            for t in dead:
                t.pop("item_id", None)
                t["dest"] = None
            _match_entries(dead, _items_since(None))
            write_m3u(pl)
            _save_state(pl)
            touched.append(pl)
            print(f"playlists: repath „{pl.get('name')}“: "
                  f"{len(dead)} veraltete Pfad-Einträge neu aufgelöst")
    except Exception as e:
        print(f"playlists: repath failed: {type(e).__name__}: {e}")
    return touched
