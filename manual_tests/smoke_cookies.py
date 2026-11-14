# -*- coding: utf-8 -*-
"""Smoke test for the YouTube cookie freshness check (Story 1.2 tooling).

Run:  python manual_tests/smoke_cookies.py
The Netscape cookie file unlocks 256 kbps downloads — until YouTube's
server-side session expires, at which point downloads quietly fall back
to 128 kbps while the file keeps looking fine. The check GETs
youtube.com/account with the jar: 200 = fresh, redirect to
accounts.google.com = stale. Cases: header parsing (youtube-only),
classification, injected-opener checks (fresh/stale/unknown), missing
file, unconfigured, and the cached status surface.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from musik import cookies as C  # noqa: E402

NETSCAPE = (
    "# Netscape HTTP Cookie File\n"
    ".google.com\tTRUE\t/\tTRUE\t1900000000\tNID\tnope\n"
    ".youtube.com\tTRUE\t/\tTRUE\t1900000000\tSID\t1.abc\n"
    ".youtube.com\tTRUE\t/\tTRUE\t1900000000\tSAPISID\tdef/ghi\n"
    ".youtube.com\tTRUE\t/\tTRUE\t0\tVISITOR_INFO1_LIVE\txyz\n"
)


def write_cookie(tmp: str, content: str) -> str:
    p = os.path.join(tmp, "cookies.txt")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(content)
    return p


def case1_parse():
    tmp = tempfile.mkdtemp(prefix="smoke-ck-")
    p = write_cookie(tmp, NETSCAPE)
    names, header = C.parse(p)
    assert names == ["SID", "SAPISID", "VISITOR_INFO1_LIVE"], names
    assert "SID=1.abc" in header and "SAPISID=def/ghi" in header, header
    assert "NID" not in header, "google.com cookie must be excluded"
    print("1) parse: youtube-only names + header OK")


def case2_classify():
    assert C.classify(200, None) == "fresh"
    assert C.classify(303, "https://accounts.google.com/ServiceLogin?x") == "stale"
    assert C.classify(302, "https://www.youtube.com/account") == "unknown"
    assert C.classify(404, None) == "unknown"
    print("2) classify: 200 fresh, google-redirect stale, rest unknown OK")


def case3_check_opener():
    tmp = tempfile.mkdtemp(prefix="smoke-ck-")
    p = write_cookie(tmp, NETSCAPE)
    C._last.clear()

    def fresh_fetch(url, headers):
        assert "SID=1.abc" in headers["Cookie"]
        return 200, None
    r = C.check(p, fetcher=fresh_fetch)
    assert r["state"] == "fresh" and r["logged_in"] is True, r

    def stale_fetch(url, headers):
        return 302, "https://accounts.google.com/ServiceLogin"
    r = C.check(p, fetcher=stale_fetch)
    assert r["state"] == "stale" and r["logged_in"] is False, r
    assert C.status()["state"] == "stale", "status serves the cache"

    def dead_fetch(url, headers):
        raise OSError("network down")
    r = C.check(p, fetcher=dead_fetch)
    assert r["state"] == "unknown", r
    print("3) check: fresh/stale/unknown via injected opener OK")


def case4_missing_and_off():
    C._last.clear()
    r = C.check(os.path.join(tempfile.mkdtemp(prefix="smoke-ck-"), "nope.txt"))
    assert r["state"] == "missing", r
    r = C.check(None)
    assert r["state"] == "off", r
    assert C.status()["state"] in ("missing", "off")
    print("4) missing file / unconfigured: honest states OK")


if __name__ == "__main__":
    case1_parse()
    case2_classify()
    case3_check_opener()
    case4_missing_and_off()
    print("smoke_cookies: alle Assertionen grün")
