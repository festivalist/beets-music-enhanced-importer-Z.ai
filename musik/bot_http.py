"""LAN-HTTP-Endpoint des Bots — Datenquelle für den Import-Monitor
(EPIC 9; ADR-0002: beobachten und Aufträge annehmen, nie selbst
importieren).

GET  /api/status  → JSON-Snapshot (Job-Queue, Ingest-Stand inkl. Units,
                    Review-Liste, _incoming-Stau)
POST /api/action  → Auftrag in die bestehende Bot-Job-Queue — derselbe
                    Worker, dasselbe ingest.lock wie Telegram-Jobs.
                    Aktionen: asis, retry, ingest

Keine Auth: Betriebsart ist LAN-only ohne Port-Forwarding — dieselbe
Postur wie die MusicGrabber-UI. Konfiguration unter
`musik: bot_http: {enabled, host, port}` (Default: an, Port 8283,
alle Interfaces).
"""

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import jobs as jobs_mod
from . import state as state_mod

DEFAULT_PORT = 8283

# Status, aus denen eine Unit per Aktion wieder angestoßen werden darf
# (deckungsgleich mit _asis_candidates im Bot).
CANDIDATE_STATUSES = ("review", "unmatched", "network", "pending")

_refs: dict | None = None
_refs_lock = threading.Lock()


def start(app, loop, queue, host: str = "", port: int = DEFAULT_PORT):
    """Startet den Endpoint als Daemon-Thread; refs merken, damit der
    HTTP-Thread Jobs in die Async-Queue des Bot-Loops legen kann."""
    global _refs
    with _refs_lock:
        _refs = {"app": app, "loop": loop, "queue": queue}
    srv = ThreadingHTTPServer((host, port), _Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, name="bot-http",
                     daemon=True).start()
    print(f"bot: http monitor auf Port {srv.server_address[1]} "
          "(LAN-only, keine Auth)", flush=True)
    return srv


def snapshot() -> dict:
    """Alles, was der Import-Monitor-Tab zeichnet — reine Lese-Sicht auf
    Job-Queue und state.json; kein Schreiben, kein Import."""
    from .paths import incoming_dir, state_dir
    from .scan import collect_audio_tree

    st = state_mod.load()
    counts = state_mod.counts(st)
    units = sorted(
        ({"path": u.get("path"), "status": u.get("status", "pending"),
          "reason": (u.get("reason") or "")[:200],
          "updated": u.get("updated"),
          "n_files": len(u.get("files") or [])}
         for u in state_mod.units(st).values()),
        key=lambda u: (u["status"], u["path"] or ""))
    sd = state_dir()
    if os.path.isdir(sd):
        from .bot import _ingest_busy  # lazy: kein Import-Zirkel

        busy = _ingest_busy(sd)
    else:
        busy = None
    try:
        backlog = len(collect_audio_tree(incoming_dir()))
    except OSError:
        backlog = None
    return {
        "jobs": jobs_mod.queue_stats(),
        "ingest": {
            "total": sum(counts.values()),
            "counts": counts,
            "busy": busy,
            "last_change": max((u["updated"] or 0 for u in units),
                               default=None),
            "units": units,
        },
        "review": [u for u in units if u["status"] == "review"],
        "backlog": {"audio_files": backlog},
    }


def handle_action(payload: dict) -> tuple[int, dict]:
    """POST /api/action: Auftrag validieren und in die Bot-Queue legen.
    Rückgabe: (HTTP-Code, Antwort-Payload)."""
    action = payload.get("action")
    if action == "asis":
        return _action_asis(payload)
    if action == "retry":
        paths = payload.get("unit_paths") or []
        label = f"{len(paths)} Unit(s)" if paths else "alle network-Units"
        return _enqueue_job(f"retry {label} (Import-Monitor)",
                            kind="retry", unit_paths=paths)
    if action == "ingest":
        return _enqueue_job("Ingest-Trigger (Import-Monitor)", kind="ingest")
    if action == "review":
        return 400, {"error": "review-apply folgt mit dem Web-Tab "
                              "(Story 9.5)"}
    return 400, {"error": f"unbekannte Aktion: {action!r}"}


def _action_asis(payload: dict) -> tuple[int, dict]:
    paths = payload.get("unit_paths") or []
    if not paths:
        return 400, {"error": "unit_paths fehlt"}
    st = state_mod.load()
    canon: list[str] = []
    bad: list[str] = []
    for p in paths:
        u = state_mod.get_unit(st, p)
        if not u or u.get("status") not in CANDIDATE_STATUSES:
            bad.append(p)
        else:
            canon.append(u.get("path") or p)
    if bad:
        return 400, {"error": "Units nicht wählbar (fremder Pfad oder "
                              "Status außerhalb "
                              f"{list(CANDIDATE_STATUSES)})",
                     "units": bad}
    return _enqueue_job(f"asis {len(canon)} unit(s) (Import-Monitor)",
                        kind="asis", unit_paths=canon)


def _enqueue_job(text: str, **fields) -> tuple[int, dict]:
    """Job persistieren (chat_id 0 = kein Telegram-Push, das Web pollt)
    und in die Async-Queue des Bot-Loops legen."""
    with _refs_lock:
        refs = _refs
    if not refs:
        return 503, {"error": "Bot-Queue nicht bereit (Bot startet noch?)"}
    job = jobs_mod.add_job(text, 0)
    job.update(fields)
    jobs_mod.update_job(job["id"], **fields)  # restart-sicher auf Disk
    fut = asyncio.run_coroutine_threadsafe(refs["queue"].put(job),
                                           refs["loop"])
    fut.result(timeout=10)
    return 200, {"queued": job["id"], "text": job["text"]}


class _Handler(BaseHTTPRequestHandler):
    """Nur /api/status (GET) und /api/action (POST); alles andere 404."""

    def log_message(self, fmt, *args) -> None:
        pass  # Journal schonen — die Status-Codes sprechen für sich

    def _json(self, code: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type",
                         "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.split("?")[0] == "/api/status":
            self._json(200, snapshot())
        else:
            self._json(404, {"error": "unbekannter Pfad"})

    def do_POST(self) -> None:
        if self.path.split("?")[0] != "/api/action":
            self._json(404, {"error": "unbekannter Pfad"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._json(400, {"error": "ungültiges JSON"})
            return
        code, out = handle_action(payload)
        self._json(code, out)
