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
        headers={"X-Plex-Token": cfg["token"]},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    root = ET.fromstring(r.text)
    out = []
    for d in root.iter("Directory"):
        if d.get("type") == "artist":  # music libraries
            out.append({"id": d.get("id"), "title": d.get("title", "")})
    return out


def _resolve_section(cfg: dict) -> tuple[str, str] | None:
    """(section id, title) — by configured name, else the first music one."""
    sections = _sections(cfg)
    for sec in sections:
        if cfg["section"] and sec["title"].lower() == cfg["section"].lower():
            return sec["id"], sec["title"]
    if not cfg["section"] and sections:
        return sections[0]["id"], sections[0]["title"]
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
            names = ", ".join(s["title"] for s in _sections(cfg)) or "none"
            return False, f"Plex: keine Musik-Section gefunden (vorhanden: {names})"
        r = requests.post(
            f"{cfg['url']}/library/sections/{sec[0]}/refresh",
            headers={"X-Plex-Token": cfg["token"]},
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return True, f"Plex-Scan der Section „{sec[1]}“ angestoßen"
        return False, f"Plex-Scan fehlgeschlagen (HTTP {r.status_code})"
    except requests.RequestException as e:
        return False, f"Plex nicht erreichbar: {str(e)[:120]}"
