"""LAN-HTTP-Endpoint des Bots — Datenquelle für den Import-Monitor
(EPIC 9; ADR-0002: beobachten und Aufträge annehmen, nie selbst
importieren).

GET  /api/status   → JSON-Snapshot (Job-Queue, Ingest-Stand inkl. Units,
                     Review-Liste, _incoming-Stau, Upgrade-Summary)
GET  /api/upgrades → kompletter Upgrade-Zustand (Story 3.3, on-demand)
POST /api/action   → Auftrag in die bestehende Bot-Job-Queue — derselbe
                     Worker, dasselbe ingest.lock wie Telegram-Jobs.
                     Aktionen: asis, retry, ingest, upgrade_scan,
                     upgrade_batch, upgrade_decide

Keine Auth: Betriebsart ist LAN-only ohne Port-Forwarding — dieselbe
Postur wie die MusicGrabber-UI. Konfiguration unter
`musik: bot_http: {enabled, host, port}` (Default: an, Port 8283,
alle Interfaces).
"""

import asyncio
import json
import os
import threading

from . import cookies as cookies_mod
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import jobs as jobs_mod
from . import spool as spool_mod
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
                 "distance": c.get("distance", ""),
                 "n_tracks": c.get("n_tracks")}
                for c in (u.get("candidates") or [])[:3]
            ],
        })
    review.sort(key=lambda u: u["path"] or "")
    sd = state_dir()
    if os.path.isdir(sd):
        from .bot import _ingest_busy  # lazy: kein Import-Zirkel

        busy = _ingest_busy(sd)
        current = None
        try:
            with open(os.path.join(sd, "ingest-current.json"),
                      encoding="utf-8") as fh:
                current = json.load(fh)
        except (OSError, ValueError):
            current = None
    else:
        busy = None
        current = None
    try:
        inc_base = incoming_dir()
        inc_files = collect_audio_tree(inc_base)
        backlog = len(inc_files)
        by_root: dict = {}
        for f in inc_files:
            r = os.path.relpath(f, inc_base).split(os.sep)[0]
            by_root[r] = by_root.get(r, 0) + 1
    except OSError:
        backlog = None
        by_root = None
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
        # Story 1.2 tooling: YouTube-Cookie-Frische (Cache aus dem
        # Cookie-Watch-Task, kein Netz im Snapshot-Pfad)
        "cookie": cookies_mod.status(),
        "ingest": {
            "total": sum(counts.values()),
            "counts": counts,
            "busy": busy,
            "current": current,
            "last_change": max((u["updated"] or 0 for u in units),
                               default=None),
            "units": units,
        },
        "review": review,
        "backlog": {"audio_files": backlog, "by_root": by_root},
        # Story 10.10: offene Nutzer-Entscheidungen im Spool — das Tab
        # zeigt den Zähler, bis der Ingest sie geflusht hat
        "spool": spool_mod.open_actions(),
        # Story 3.3: Upgrade-Kandidaten als Leichte-Sicht (Counts + Batches;
        # die Track-Liste holt das Tab on-demand über /api/upgrades)
        "upgrades": _upgrades_summary_safe(),
    }


def _upgrades_summary_safe() -> dict:
    """Snapshot-Feld für Story 3.3 — Fehler hier dürfen den Monitor nicht
    leermachen (z. B. korruptes state/upgrades.json)."""
    try:
        from . import upgrades as upgrades_mod

        return upgrades_mod.summary()
    except Exception:
        return {}


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
    if action == "upgrade_scan":
        return _enqueue_job("Upgrade-Scan (Import-Monitor)",
                            kind="upgrade_scan")
    if action == "upgrade_batch":
        return _action_upgrade_batch(payload)
    if action == "upgrade_decide":
        return _action_upgrade_decide(payload)
    return 400, {"error": f"unbekannte Aktion: {action!r}"}


def _action_upgrade_batch(payload: dict) -> tuple[int, dict]:
    """Story 3.3: einen geplanten Upgrade-Batch zum Nachladen anstoßen.
    Erlaubt nur Batches, die noch nicht laufen/fertig sind."""
    from . import upgrades as upgrades_mod

    bid = (payload.get("batch_id") or "").strip()
    if not bid:
        return 400, {"error": "batch_id fehlt"}
    batch = next((b for b in upgrades_mod.load().get("batches", [])
                  if b.get("id") == bid), None)
    if batch is None:
        return 400, {"error": f"unbekannter Batch: {bid!r} (nach einem "
                              "Rescan den neuen Plan benutzen)"}
    if batch.get("status") not in ("queued", "error", "ingest-pending",
                                   "partial"):
        return 400, {"error": f"Batch {bid} ist {batch.get('status')} — "
                              "nicht anstoßbar"}
    return _enqueue_job(f"Upgrade-Batch {bid} nachladen "
                        f"({batch.get('n')} Tracks)",
                        kind="upgrade_batch", batch_id=bid)


def _action_upgrade_decide(payload: dict) -> tuple[int, dict]:
    """Story 3.3: Behalten/Freigeben je Upgrade-Kandidat — serialisiert
    über die Job-Queue, damit nie parallel zum Batch-Executor geschrieben
    wird."""
    from . import upgrades as upgrades_mod

    ids = payload.get("item_ids") or []
    decision = payload.get("decision") or None
    if decision not in ("keep", None):
        return 400, {"error": "decision muss 'keep' oder null sein"}
    if not ids:
        return 400, {"error": "item_ids fehlt"}
    known = {c.get("id") for c in
             upgrades_mod.load().get("candidates", [])}
    canon, bad = [], []
    for iid in ids:
        try:
            key = int(iid)
        except (TypeError, ValueError):
            bad.append(iid)
            continue
        (canon if key in known else bad).append(key)
    if bad:
        return 400, {"error": "Item-Ids gehören nicht zum aktuellen "
                              "Kandidaten-Plan (Rescan?)", "items": bad[:5]}
    label = "behalten" if decision == "keep" else "freigeben"
    return _enqueue_job(f"Upgrade: {len(canon)} Track(s) {label}",
                        kind="upgrade_decide", item_ids=canon,
                        decision=decision)


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
    """GET /api/status (JSON), GET /monitor (+ / leitet dorthin),
    POST /api/action; sonst 404."""

    def log_message(self, fmt, *args) -> None:
        pass  # Journal schonen — die Status-Codes sprechen für sich

    def _json(self, code: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type",
                         "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # CORS (Story 9.4): seit 11.7 läuft der Monitor hier same-origin
        # (:/monitor), der Header bleibt für ältere Depot-Depots/externen
        # LAN-Zugriff bestehen. LAN-only ohne Credentials — "*" ist hier
        # die richtige Postur (ADR-0001).
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

    def _monitor_page(self) -> None:
        """Story 11.7: der Import-Monitor wird vom Bot SELBST ausgeliefert.
        MG 4.4.1+ erzwingt eine CSP mit connect-src 'self' (HTTP-Header,
        core/middleware.py — für das Static-Overlay unantastbar), womit
        Cross-Origin-Fetches des Overlay-Tabs gegen :8283 im Browser
        blockiert werden. Same-origin hier braucht keine Ausnahme."""
        page = (os.path.join(os.path.dirname(__file__), "monitor.html"))
        try:
            with open(page, "rb") as fh:
                body = fh.read()
        except OSError:
            self._json(500, {"error": "monitor.html fehlt"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/status":
            self._json(200, snapshot())
        elif path == "/api/upgrades":
            # Story 3.3: kompletter Upgrade-Zustand — on-demand (Tab
            # öffnet die Sektion / Scan ändert scanned_ts), nicht im 5-s-Poll
            from . import upgrades as upgrades_mod

            self._json(200, upgrades_mod.detail())
        elif path == "/monitor":
            self._monitor_page()
        elif path == "/":
            self.send_response(302)
            self.send_header("Location", "/monitor")
            self.send_header("Content-Length", "0")
            self.end_headers()
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
