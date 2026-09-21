"""Plex Media Server integration: library refresh + playlist upload.

Config (config.yaml, under the `musik:` section):

    plex:
        url: http://plexpi:32400     # PMS base url
        token: XXX                   # X-Plex-Token
        section: Musik               # library name (optional; first music
                                     # section is used when omitted)
        playlists: true              # upload job playlists as m3u (default)
        playlist_attempts: 5         # upload retries while PMS scans tracks
        playlist_wait: 10            # seconds between retries
        # playlist_dir: D:\\plex-playlists  # default: <library>/_playlists

Everything here is best-effort: refresh/upload failures never fail an
import.
"""

import os
import time
import xml.etree.ElementTree as ET

import requests

from .paths import bootstrap, musik_config

TIMEOUT = 20
_CLIENT_ID = "musik-bot-import"


def _headers(cfg: dict) -> dict:
    # newer PMS builds (1.4x) reject API writes without a client identifier
    return {
        "X-Plex-Token": cfg["token"],
        "X-Plex-Client-Identifier": _CLIENT_ID,
    }


def plex_config() -> dict | None:
    """Configured plex section or None (integration disabled)."""
    cfg = (musik_config().get("plex") or {})
    url = (cfg.get("url") or "").strip().rstrip("/")
    token = (cfg.get("token") or "").strip()
    if not url or not token:
        return None
    return {
        "url": url,
        "token": token,
        "section": (cfg.get("section") or "").strip(),
        "playlists": cfg.get("playlists", True),
        "playlist_attempts": int(cfg.get("playlist_attempts", 5)),
        "playlist_wait": float(cfg.get("playlist_wait", 10)),
    }


def _sections(cfg: dict) -> list[dict]:
    r = requests.get(
        f"{cfg['url']}/library/sections",
        headers=_headers(cfg),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    root = ET.fromstring(r.text)
    out = []
    for d in root.iter("Directory"):
        if d.get("type") != "artist":  # music libraries only
            continue
        # PMS builds differ: older carry a plain numeric `id`, newer put
        # the id in `key` — either as the section path
        # ("/library/sections/3") or as the bare number ("3")
        sid = (d.get("id") or "").strip()
        if not sid:
            sid = (d.get("key") or "").rstrip("/").rsplit("/", 1)[-1].strip()
        entry = {"id": sid, "title": d.get("title", "")}
        if not sid:
            entry["raw"] = " ".join(
                f"{k}={v}" for k, v in sorted(d.attrib.items()))[:200]
        out.append(entry)
    return out


def _resolve_section(cfg: dict) -> tuple[str, str] | None:
    """(section id, title) — by configured name, else the first music one."""
    sections = _sections(cfg)
    for sec in sections:
        if not sec["id"]:
            continue  # unresolvable -> cannot be refreshed
        if cfg["section"] and sec["title"].lower() == cfg["section"].lower():
            return sec["id"], sec["title"]
    if not cfg["section"]:
        for sec in sections:
            if sec["id"]:
                return sec["id"], sec["title"]
    return None


def refresh_library() -> tuple[bool, str]:
    """Ask Plex to rescan the music library. Returns (ok, message)."""
    bootstrap()
    cfg = plex_config()
    if not cfg:
        return False, ""  # not configured -> caller stays silent
    try:
        sec = _resolve_section(cfg)
        if not sec:
            parts = []
            for s in _sections(cfg):
                if s["id"]:
                    parts.append(f"{s['title']} (id {s['id']})")
                else:
                    parts.append(f"{s['title']} — ohne id! Attribute: {s.get('raw', '')}")
            return False, ("Plex: keine nutzbare Musik-Section gefunden "
                           f"(vorhanden: {'; '.join(parts) or 'none'})")
        r = requests.post(
            f"{cfg['url']}/library/sections/{sec[0]}/refresh",
            headers=_headers(cfg),
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return True, f"Plex-Scan der Section „{sec[1]}“ (id {sec[0]}) angestoßen"
        body = (r.text or "").strip()[:150]
        return False, (f"Plex-Scan fehlgeschlagen (Section „{sec[1]}“ id={sec[0]}, "
                       f"HTTP {r.status_code}" + (f": {body}" if body else "") + ")")
    except requests.RequestException as e:
        return False, f"Plex nicht erreichbar: {str(e)[:120]}"


# --------------------------------------------------------------------------
# playlist upload (m3u -> server-side playlist, shows up in Plexamp)
# --------------------------------------------------------------------------

def _find_uploaded_playlist(cfg: dict, m3u_path: str) -> dict | None:
    """The playlist PMS created from our m3u. Imported playlists carry the
    source file path in their guid (same trick python-plexapi uses); slash
    style may differ between PMS platforms, so both sides are normalized."""
    r = requests.get(
        f"{cfg['url']}/playlists",
        headers=_headers(cfg),
        params={"playlistType": "audio"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    suffix = os.path.abspath(m3u_path).replace("\\", "/").lower()
    for pl in ET.fromstring(r.text).iter("Playlist"):
        guid = (pl.get("guid") or "").replace("\\", "/").lower()
        if guid.endswith(suffix):
            return {
                "id": pl.get("ratingKey", ""),
                "title": pl.get("title", ""),
                "leaf_count": int(pl.get("leafCount", "0") or 0),
            }
    return None


def _rename_playlist(cfg: dict, playlist_id: str, title: str) -> bool:
    r = requests.put(
        f"{cfg['url']}/playlists/{playlist_id}",
        headers=_headers(cfg),
        params={"title": title},
        timeout=TIMEOUT,
    )
    return r.status_code == 200


def upload_playlist(m3u_path: str, title: str | None = None) -> tuple[bool, str]:
    """Import an m3u file server-side (POST /playlists/upload — the same
    endpoint python-plexapi's m3ufilepath uses).

    PMS matches entries by file path against the scanned library, so this
    runs after a library refresh and retries while the scan catches up: a
    re-upload of the same file REPLACES the playlist (idempotent). The
    playlist is renamed to `title` (without that, its name would be the
    m3u filename). Returns (ok, message).
    """
    bootstrap()
    cfg = plex_config()
    if not cfg or not cfg.get("playlists", True):
        return False, ""  # not configured / disabled -> caller stays silent
    m3u_path = os.path.abspath(m3u_path)
    if not os.path.isfile(m3u_path):
        return False, f"Plex-Playlist: Datei fehlt: {m3u_path}"
    name = title or os.path.splitext(os.path.basename(m3u_path))[0]
    try:
        sec = _resolve_section(cfg)
        if not sec:
            return False, "Plex-Playlist: keine nutzbare Musik-Section gefunden"
        last_err = ""
        for attempt in range(max(1, cfg["playlist_attempts"])):
            if attempt:
                time.sleep(cfg["playlist_wait"])
            r = requests.post(
                f"{cfg['url']}/playlists/upload",
                headers=_headers(cfg),
                params={"sectionID": sec[0], "path": m3u_path},
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                body = (r.text or "").strip()[:150]
                last_err = (f"HTTP {r.status_code}"
                            + (f": {body}" if body else ""))
                continue
            pl = _find_uploaded_playlist(cfg, m3u_path)
            if pl is None:
                last_err = "Playlist wurde nicht erzeugt"
                continue
            if pl["leaf_count"] > 0:
                if name and pl["title"] != name:
                    _rename_playlist(cfg, pl["id"], name)
                return True, (f"Plex-Playlist „{name}“: {pl['leaf_count']}"
                              f" Track(s) in Plexamp verfügbar")
            # tracks not scanned yet — replacing on the next round
            last_err = "0 Tracks (Plex hat die neuen Dateien noch nicht gescannt)"
        hint = " — später erneut: musik plex --playlist " \
               f"\"{os.path.splitext(os.path.basename(m3u_path))[0]}\""
        return False, f"Plex-Playlist-Import fehlgeschlagen ({last_err}){hint}"
    except requests.RequestException as e:
        return False, f"Plex nicht erreichbar: {str(e)[:120]}"
    except (ET.ParseError, ValueError) as e:
        return False, f"Plex-Playlist: unerwartete Server-Antwort: {e}"
