"""Plex Media Server integration: trigger a library scan after imports.

Config (config.yaml, under the `musik:` section):

    plex:
        url: http://plexpi:32400     # PMS base url
        token: XXX                   # X-Plex-Token
        section: Musik               # library name (optional; first music
                                     # section is used when omitted)

Everything here is best-effort: refresh failures never fail an import.
"""

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
    return {"url": url, "token": token, "section": (cfg.get("section") or "").strip()}


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
