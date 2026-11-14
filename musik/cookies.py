"""YouTube cookie freshness (Story 1.2 tooling, 2026-11-14).

The Netscape cookie file unlocks 256 kbps downloads and fewer bot
challenges — until YouTube's server-side session expires. The file then
still looks fine while downloads quietly fall back to 128 kbps
(2026-11-13 live case: the whole "Klare Kante" playlist came in at
~130 kbps). This module actively validates the session: GET
youtube.com/account with the jar — 200 means fresh, a redirect to
accounts.google.com means the session is gone. Results are cached so
the snapshot/monitor paths never hit the network; the bot re-checks on
a timer and notifies the allowlist chats on the fresh→stale edge.
"""

import json
import os
import time
import urllib.request

# Revalidate at most this often (the bot's timer honours this).
CHECK_INTERVAL = 6 * 3600
_YT_ACCOUNT_URL = "https://www.youtube.com/account"
_UA = "musik-cookie-check/1.0 (festivalist)"

# Cache: {checked_at, result}. status() serves it without any network.
_last: dict = {}


def parse(path: str) -> tuple[list[str], str]:
    """Names + a Cookie header from a Netscape file, youtube.com only."""
    names: list[str] = []
    pairs: list[str] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("#") or not line.strip():
                    continue
                fields = line.rstrip("\n").split("\t")
                if len(fields) < 7:
                    continue
                domain, name, value = fields[0], fields[5], fields[6]
                if "youtube.com" not in domain:
                    continue
                names.append(name)
                pairs.append(f"{name}={value}")
    except OSError:
        return [], ""
    return names, "; ".join(pairs)


def classify(status_code: int, location: str | None) -> str:
    """200 → fresh; a redirect to Google's login → stale; else unknown."""
    if status_code == 200:
        return "fresh"
    if 300 <= status_code < 400 and location and \
            "accounts.google.com" in location:
        return "stale"
    return "unknown"


def check(path: str | None, fetcher=None) -> dict:
    """Validate the cookie session (fetcher injectable for tests).

    Result dict: state fresh/stale/unknown/missing/off, logged_in,
    cookie_names, file_age_days, checked_at, detail. Caches into _last.
    """
    result: dict = {"state": "off", "logged_in": None, "cookie_names": [],
                    "file_age_days": None, "checked_at": time.time(),
                    "detail": ""}
    if not path:
        result["detail"] = "kein Cookie konfiguriert (Downloads anonym, 128 kbps)"
        _last.update(result)
        return result
    if not os.path.isfile(path):
        result["state"] = "missing"
        result["detail"] = "Cookie-Datei fehlt (Pfad falsch/Datei gelöscht)"
        _last.update(result)
        return result
    try:
        result["file_age_days"] = round(
            (time.time() - os.path.getmtime(path)) / 86400, 1)
    except OSError:
        pass
    names, header = parse(path)
    result["cookie_names"] = names
    fetcher = fetcher or _http_get
    try:
        code, location = fetcher(_YT_ACCOUNT_URL, {
            "Cookie": header, "User-Agent": _UA,
            "Accept-Language": "de,en;q=0.8",
        })
    except Exception as exc:
        result["state"] = "unknown"
        result["detail"] = f"Prüfung nicht möglich: {str(exc)[:80]}"
        _last.update(result)
        return result
    verdict = classify(code, location)
    result["state"] = verdict
    result["logged_in"] = True if verdict == "fresh" else \
        (False if verdict == "stale" else None)
    result["detail"] = {
        "fresh": "Session gültig — Downloads mit Account-Qualität",
        "stale": "Session abgelaufen — Downloads fallen auf 128 kbps zurück",
        "unknown": "Antwort nicht eindeutig — Datei bei Bedarf erneuern",
    }[verdict]
    _last.update(result)
    return result


def status() -> dict:
    """The cached verdict (no network). 'unchecked' before the first run."""
    return dict(_last) if _last else {
        "state": "unchecked", "logged_in": None, "cookie_names": [],
        "file_age_days": None, "checked_at": None,
        "detail": "noch nicht geprüft",
    }


def _http_get(url: str, headers: dict) -> tuple[int, str | None]:
    """Real opener: GET without following redirects; returns (code, location)."""
    req = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(req, timeout=15) as r:
        return r.status, r.headers.get("Location")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):  # noqa: N802
        return None  # surfacing the 3xx is the whole point
