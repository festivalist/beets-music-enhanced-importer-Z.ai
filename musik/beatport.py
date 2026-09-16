"""beatport4 token maintenance.

The plugin reuses a valid access token but cannot refresh an expired one
by itself — it falls back to username/password and, on failure, to an
interactive prompt that kills unattended imports. This module refreshes
the token via the standard OAuth flow before the plugin ever sees it.
"""

import json
import os
import re
import time

import requests

API_BASE = "https://api.beatport.com/v4"
_SCRIPT_SRC_PATTERN = re.compile(r"src=.(.*js)")
_CLIENT_ID_PATTERN = re.compile(r"API_CLIENT_ID: \'(.*)\'")

_client_id_cache: str | None = None


def _tokenfile_path() -> str | None:
    from .paths import PROJECT_DIR

    p = os.path.join(PROJECT_DIR, "beatport_token.json")
    return p if os.path.isfile(p) else None


def _fetch_client_id(log=None) -> str:
    global _client_id_cache
    if _client_id_cache:
        return _client_id_cache
    html = requests.get(f"{API_BASE}/docs/", timeout=30).content.decode(
        "utf-8"
    )
    last_err = None
    for url in _SCRIPT_SRC_PATTERN.findall(html):
        try:
            js = requests.get(
                f"https://api.beatport.com{url}", timeout=30
            ).content.decode("utf-8")
        except requests.exceptions.RequestException as e:
            last_err = e
            continue
        m = _CLIENT_ID_PATTERN.findall(js)
        if m:
            _client_id_cache = m[0]
            return _client_id_cache
    raise RuntimeError(f"no API_CLIENT_ID found (last error: {last_err})")


def token_expired(path: str) -> bool:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return float(data.get("expires_at", 0)) <= time.time() + 30
    except Exception:
        return True


def refresh_token_file(path: str, log=None) -> bool:
    """Refresh an expired access token in-place via the refresh grant.

    Returns True when the file afterwards holds a fresh token.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        refresh = data.get("refresh_token")
        if not refresh:
            return False
        client_id = _fetch_client_id()
        r = requests.post(
            f"{API_BASE}/auth/o/token/",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": client_id,
            },
            timeout=30,
        )
        if not r.ok:
            if log:
                log.warning("beatport token refresh failed: HTTP {}",
                            r.status_code)
            return False
        resp = r.json()
        if "access_token" not in resp:
            return False
        new = {
            "access_token": resp["access_token"],
            "expires_at": time.time() + int(resp.get("expires_in", 0)),
            "refresh_token": resp.get("refresh_token", refresh),
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new, f)
        os.replace(tmp, path)
        if log:
            log.debug("beatport access token refreshed")
        return True
    except Exception as e:
        if log:
            log.warning("beatport token refresh error: {}", e)
        return False


def ensure_fresh_token(log=None) -> bool:
    """Make sure beatport_token.json holds a non-expired token if we can."""
    path = _tokenfile_path()
    if path is None:
        return False
    if not token_expired(path):
        return True
    return refresh_token_file(path, log=log)
