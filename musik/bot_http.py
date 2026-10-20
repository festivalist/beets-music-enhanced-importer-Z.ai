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
# review.csv-Vokabular (review.py) + reviewbare Ausgangs-Statusse
REVIEW_DECISIONS = ("accept", "accept2", "override", "unmatched", "ignore")
REVIEWABLE_STATUSES = ("review", "unmatched", "network")

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
    # Review-Liste reicher als die slim Units: Kandidaten-Labels für die
    # Aktions-Buttons im Tab (Story 9.5), ohne ids — die Apply-Logik liest
    # sie selbst aus dem state.
    review = []
    for u in state_mod.units(st).values():
        if u.get("status") != "review":
            continue
        review.append({
            "path": u.get("path"),
            "reason": (u.get("reason") or "")[:200],
            "updated": u.get("updated"),
            "n_files": len(u.get("files") or []),
            "guessed": {k: (u.get("guessed") or {}).get(k, "")
                        for k in ("artist", "album")},
            "candidates": [
                {"source": c.get("source", ""), "artist": c.get("artist", ""),
                 "album": c.get("album", ""), "year": c.get("year", ""),
                 "distance": c.get("distance", "")}
                for c in (u.get("candidates") or [])[:3]
            ],
        })
    review.sort(key=lambda u: u["path"] or "")
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
    all_jobs = [
        {"id": j.get("id"), "status": j.get("status"),
         "kind": j.get("kind"),
         "text": (j.get("text") or "")[:80],
         "summary": (j.get("summary") or "")[:200],
         "created": j.get("created"), "finished": j.get("finished")}
        for j in jobs_mod.load_jobs()[-30:]
    ]
    return {
        "jobs": jobs_mod.queue_stats(),
        # komplette Historie (slim) — das Tab verfolgt damit die eigenen
        # Aufträge bis zum ECHTEN Ergebnis (Story 9.6, kein stilles
        # Verfallen mehr)
        "jobs_all": list(reversed(all_jobs)),
        "ingest": {
            "total": sum(counts.values()),
            "counts": counts,
            "busy": busy,
            "last_change": max((u["updated"] or 0 for u in units),
                               default=None),
            "units": units,
        },
        "review": review,
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
        return _action_review(payload)
    return 400, {"error": f"unbekannte Aktion: {action!r}"}


def _action_review(payload: dict) -> tuple[int, dict]:
    """Review-Entscheidungen (review.csv-Vokabular) in die Queue legen;
    der Executor läuft unter dem ingest.lock."""
    rows = payload.get("decisions") or []
    if not rows:
        return 400, {"error": "decisions fehlt"}
    st = state_mod.load()
    bad: list[str] = []
    canon: list[dict] = []
    for d in rows:
        unit = state_mod.get_unit(st, d.get("unit_path", ""))
        decision = (d.get("decision") or "").strip().lower()
        if (not unit or decision not in REVIEW_DECISIONS
                or unit.get("status") not in REVIEWABLE_STATUSES):
            bad.append(d.get("unit_path", "?"))
            continue
        canon.append({
            "unit_path": unit.get("path") or d["unit_path"],
            "decision": decision,
            "override_artist": (d.get("override_artist") or "").strip(),
            "override_album": (d.get("override_album") or "").strip(),
            "override_mbid": (d.get("override_mbid") or "").strip(),
            "notes": (d.get("notes") or "").strip(),
        })
    if bad:
        return 400, {"error": "Entscheidungen nicht ausführbar (fremder "
                              "Pfad, unbekannte decision oder Status "
                              f"außerhalb {list(REVIEWABLE_STATUSES)})",
                     "units": bad}
    if not canon:
        return 400, {"error": "keine gültigen Entscheidungen"}
    return _enqueue_job(f"review apply {len(canon)} (Import-Monitor)",
                        kind="review", decisions=canon)


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
        # CORS (Story 9.4): der Monitor-Tab läuft im Browser auf der
        # MG-Origin (:38274) und liest hier cross-port. LAN-only ohne
        # Credentials — "*" ist hier die richtige Postur (ADR-0001).
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods",
                         "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:  # Preflight für POST mit JSON-Body
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

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
