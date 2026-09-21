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
        from .fetch import _cookie_path, _fetch_config

        cookies = _cookie_path(_fetch_config())
    except Exception:
        pass
    info = _ytdlp_fetch(url, cookies)
    if info is None:
        return None
    return _order_from_info(info, job.files)


def _job_label(job_id: str) -> str:
    """Human-ish name from 'fetch-20260921-123001-spotify-bestsongs'."""
    parts = job_id.split("-", 3)
    return (parts[3] if len(parts) > 3 else job_id).strip("-")


def prepare(job) -> list[dict] | None:
    """Collect playlist specs for a fetch job before the import runs.

    Returns [{name, entries:[...]}] or None when the query was no playlist
    (or nothing usable was found). Call build() with the same result after
    the import chain; both never raise — a playlist problem must not be
    able to fail an import.
    """
    try:
        if not is_playlist_query(job.query) or not job.files:
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
            # and order from yt-dlp metadata; without that, mtime is the
            # best guess (paced downloads finish in playlist order).
            name = None
            entries = None
            if job.kind == "youtube":
                got = _youtube_order(job)
                if got:
                    name, entries = got
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
    from beets import config as beets_config
    from beets.library import Library

    return Library(
        beets_config["library"].as_filename(),
        beets_config["directory"].as_filename(),
    )


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
    by rebuild to fill gaps after a later /asis)."""
    lib = _lib()
    out = []
    for it in lib.items():
        if ids_before is not None and it.id in ids_before:
            continue
        out.append({
            "id": it.id,
            "path": os.fsdecode(it.path),
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


def write_m3u(pl: dict) -> str:
    """(Re)write the .m3u for a playlist state; returns its path."""
    path = os.path.join(m3u_dir(), _safe_filename(pl["name"]) + ".m3u")
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
            # keep earlier matches (item_id) stable across rebuilds
            prev = None
            old = _load_state(sf)
            if old and old.get("name") == spec["name"]:
                prev = {t["file"]: t for t in old.get("tracks", [])}
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
            write_m3u(pl)
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


def upload(states: list[dict]) -> list[str]:
    """Upload playlist states to Plex (after a library refresh). Returns
    message lines; empty when Plex is not configured or nothing to do."""
    from . import plex as plex_mod

    msgs: list[str] = []
    for pl in states:
        if not pl.get("m3u"):
            continue
        ok, note = plex_mod.upload_playlist(pl["m3u"], title=pl.get("name"))
        if ok:
            msgs.append(f"🎵 {note}")
            pl["plex"] = {"uploaded": time.time(), "message": note}
            _save_state(pl)
        elif note:  # configured but failed
            msgs.append(f"⚠️ {note}")
    return msgs


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
    roots = [os.path.normcase(os.path.normpath(p)) for p in unit_paths if p]
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
            job_root = os.path.normcase(os.path.normpath(
                pl.get("job_dir")
                or os.path.join(incoming_dir(), pl.get("job_id", ""))))
            if not any(r == job_root or r.startswith(job_root + os.sep)
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
