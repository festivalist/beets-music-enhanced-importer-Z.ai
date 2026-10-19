# -*- coding: utf-8 -*-
"""Smoke test for the bot's LAN-HTTP endpoint (Story 9.1, Import-Monitor).

Run:  python manual_tests/smoke_bot_http.py
Starts the real ThreadingHTTPServer on an ephemeral port with a real
asyncio loop (like the bot would), against a seeded temp state.json and
patched path bindings. Checks the GET snapshot (counts, review list,
backlog), the POST actions (asis enqueue + validation, retry enqueue +
executor flip, ingest trigger, review-Answer 9.5) and error codes.
"""

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import musik.bot as B  # noqa: E402
import musik.bot_http as BH  # noqa: E402
import musik.jobs as jobs_mod  # noqa: E402
import musik.paths as paths_mod  # noqa: E402
import musik.state as state_mod  # noqa: E402


def _seed_state(sd: str) -> None:
    os.makedirs(sd, exist_ok=True)
    now = time.time()
    st = {"meta": {}, "units": {}}
    for path, status, reason, n_files in (
            (r"C:\lib\auto-album", "auto", "", 1),
            (r"C:\lib\review-album", "review", "low conf", 2),
            (r"C:\lib\network-album", "network", "rate limit", 1)):
        state_mod.put_unit(st, {
            "path": path, "status": status, "reason": reason,
            "updated": now - n_files * 30,
            "files": [f"{path}\\f{i}" for i in range(n_files)]})
    state_mod.save(st)


def _get(port: str, path: str, method: str = "GET") -> tuple[int, dict, dict]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if body.strip() else {}), \
                dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8")), dict(e.headers)


def _post(port: str, path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        sd = os.path.join(tmp, "state")
        inc = os.path.join(tmp, "incoming")
        os.makedirs(inc, exist_ok=True)
        for name in ("one.mp3", "two.flac"):
            open(os.path.join(inc, name), "wb").close()

        # Patches ZUERST (alle state_dir/incoming_dir-Bindungen → tmp),
        # dann seedet der Test über die echte state-API in tmp
        paths_mod.state_dir = lambda: sd
        paths_mod.incoming_dir = lambda: inc
        jobs_mod.state_dir = lambda: sd  # Module-Bindung in jobs.py
        _seed_state(sd)

        loop = asyncio.new_event_loop()
        threading.Thread(target=loop.run_forever, daemon=True).start()
        queue = asyncio.Queue()
        srv = BH.start(None, loop, queue, host="127.0.0.1", port=0)
        port = srv.server_address[1]

        def qget() -> dict:
            fut = asyncio.run_coroutine_threadsafe(queue.get(), loop)
            return fut.result(timeout=5)

        try:
            # 0) CORS + Preflight (Story 9.4: Monitor-Tab liest cross-port)
            code, _snap, hdr = _get(port, "/api/status")
            assert hdr.get("Access-Control-Allow-Origin") == "*", hdr
            code, _out, hdr = _get(port, "/api/status", method="OPTIONS")
            assert code == 204, code
            assert hdr.get("Access-Control-Allow-Methods") == \
                "GET, POST, OPTIONS", hdr

            # 1) GET-Snapshot
            code, snap, _hdr = _get(port, "/api/status")
            assert code == 200, code
            assert snap["ingest"]["total"] == 3, snap["ingest"]
            assert snap["ingest"]["counts"].get("review") == 1, snap
            assert snap["ingest"]["busy"] in (True, False, None)
            assert len(snap["review"]) == 1, snap["review"]
            assert snap["review"][0]["path"].endswith("review-album")
            assert snap["backlog"]["audio_files"] == 2, snap["backlog"]
            assert snap["jobs"]["queued"] == 0, snap["jobs"]

            # 2) asis-Aktion: validiert, canonical, chat_id 0, persistiert
            code, out = _post(port, "/api/action", {
                "action": "asis",
                "unit_paths": [r"C:\lib\review-album"]})
            assert code == 200, (code, out)
            job = qget()
            assert job["kind"] == "asis", job
            assert job["chat_id"] == 0, job
            assert job["unit_paths"] == [r"C:\lib\review-album"], job
            stored = [j for j in jobs_mod.load_jobs()
                      if j["id"] == out["queued"]]
            assert stored and stored[0]["kind"] == "asis", stored

            # 3) asis-Validierung: fremder Pfad → 400, nichts enqueued
            code, out = _post(port, "/api/action", {
                "action": "asis", "unit_paths": [r"C:\lib\nope"]})
            assert code == 400, (code, out)
            assert "nicht wählbar" in out["error"], out

            # 4) retry: enqueue + Executor-Flip network → pending
            code, out = _post(port, "/api/action", {
                "action": "retry",
                "unit_paths": [r"C:\lib\network-album"]})
            assert code == 200, (code, out)
            rjob = qget()
            assert rjob["kind"] == "retry", rjob
            sent: list[str] = []
            B._execute_retry(rjob, sent.append)
            fresh = state_mod.get_unit(state_mod.load(),
                                       r"C:\lib\network-album")
            assert fresh["status"] == "pending", fresh
            assert any("auf pending" in s for s in sent), sent

            # 5) ingest-Trigger nur enqueue (kein Echtlauf im Test)
            code, out = _post(port, "/api/action", {"action": "ingest"})
            assert code == 200, (code, out)
            ijob = qget()
            assert ijob["kind"] == "ingest", ijob

            # 6) review → 400 mit 9.5-Hinweis; Unbekanntes → 400; 404
            code, out = _post(port, "/api/action", {"action": "review"})
            assert code == 400 and "9.5" in out["error"], (code, out)
            code, out = _post(port, "/api/action", {"action": "hokuspokus"})
            assert code == 400, (code, out)
            code, _out, _hdr = _get(port, "/api/nope")
            assert code == 404, code
        finally:
            srv.shutdown()
            loop.call_soon_threadsafe(loop.stop)

    print("smoke_bot_http: alle Assertionen grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
