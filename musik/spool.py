"""Aktionsspool für den Import-Monitor (Story 9.6).

Schreibende Monitor-Aktionen (review/asis/retry) dürfen nicht still
verfallen, wenn der ingest.lock durch den Dauerbetrieb des Ingest-Timers
belegt ist (Befund 2026-10-20: patience=120 prallt an >1-h-Zyklen ab).
Der Bot legt sie hier ab, und `cmd_ingest` arbeitet den Spool bei jedem
Zyklusbeginn selbst ab — unter dem Lock, den der Ingest ohnehin hält.
Der Ingest bleibt damit die einzige schreibende Instanz; die Job-Records
bekommen das echte Ergebnis statt einer Deferral.

Datei: state/action-spool.json; Einträge
  {"kind": "review"|"asis"|"retry", "job_id": "...", "payload": {...},
   "queued": <epoch>}
Nur der Bot-Prozess schreibt Einträge (threading.Lock + atomarer
Replace); nur der Ingest entnimmt (Rename + Exists-Check gegen die
Clobber-Falle, wenn während der Entnahme ein neuer Eintrag landet).
"""

import json
import os
import tempfile
import threading
import time

from .paths import state_dir

_lock = threading.Lock()


def _file() -> str:
    return os.path.join(state_dir(), "action-spool.json")


def _load() -> list:
    try:
        with open(_file(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def add(kind: str, job_id: str, payload: dict) -> None:
    with _lock:
        entries = _load()
        entries.append({"kind": kind, "job_id": job_id,
                        "payload": payload, "queued": time.time()})
        d = state_dir()
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(entries, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, _file())
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise


def take() -> list:
    """Alle Einträge atomar entnehmen. Der leere Spool wird nur
    angelegt, wenn nicht inzwischen (Bot-Seite) schon ein neuerer
    Eintrag geschrieben wurde."""
    with _lock:
        src = _file()
        if not os.path.isfile(src):
            return []
        work = src + ".draining"
        os.replace(src, work)
        try:
            with open(work, encoding="utf-8") as fh:
                entries = json.load(fh)
        except (OSError, ValueError):
            entries = []
        os.remove(work)
        if not os.path.exists(src):
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(src),
                                       suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump([], fh)
            os.replace(tmp, src)
        return entries


def flip_retry(paths: list[str]) -> int:
    """network/unmatched-Units zurück auf pending setzen (Kern der
    Retry-Aktion; ohne Pfadfilter = alle network/unmatched-Units). Mit
    expliziten Pfaden sind auch error-Units retrybar (Story 9.11: nach
    einem Fix den Lauf wiederholen — die Sammel-Aktion bleibt
    konservativ). Aufrufer koordiniert den ingest.lock."""
    from . import state as state_mod

    targets = {os.path.normcase(os.path.normpath(p)) for p in paths}
    retryable = ("network", "unmatched", "error") if targets \
        else ("network", "unmatched")
    st = state_mod.load()
    n = 0
    for u in state_mod.units(st).values():
        up = os.path.normcase(os.path.normpath(u.get("path") or ""))
        if targets and up not in targets:
            continue
        if u.get("status") in retryable:
            state_mod.set_status(u, "pending", "")
            n += 1
    state_mod.save(st)
    return n


def drain_and_execute(log=print) -> int:
    """Vom Ingest bei ZYKLUSBEGINN aufrufen (wir stehen unter dem
    ingest.lock): alle gespoolten Aktionen ausführen und die zugehörigen
    Job-Records mit dem echten Ergebnis fortschreiben."""
    entries = take()
    if not entries:
        return 0
    log(f"spool: {len(entries)} Aktion(en) aus dem Monitor-Spool")
    from . import asis as asis_mod
    from . import jobs as jobs_mod
    from . import review as review_mod

    for e in entries:
        kind = e.get("kind")
        job_id = e.get("job_id")
        payload = e.get("payload") or {}
        try:
            if kind == "review":
                applied, msgs = review_mod.apply_decisions_rows(
                    payload.get("decisions") or [])
                summary = (f"📋 Review (nachgereicht): {applied} "
                           f"angewandt\n" + "\n".join(msgs[:10]))
                status = "done"
            elif kind == "asis":
                lines, failed = asis_mod.import_units(
                    payload.get("unit_paths") or [])
                summary = "\n".join(lines)[:1500] or "fertig"
                status = "error" if failed else "done"
            elif kind == "retry":
                n = flip_retry(payload.get("unit_paths") or [])
                summary = (f"🔁 {n} Unit(s) auf pending — dieser Lauf "
                           "versucht sie erneut.")
                status = "done"
            else:
                summary = f"unbekannte Spool-Aktion {kind!r}"
                status = "error"
        except Exception as exc:
            summary = (f"❌ Spool-Aktion fehlgeschlagen: "
                       f"{type(exc).__name__}: {str(exc)[:200]}")
            status = "error"
        if job_id:
            jobs_mod.update_job(job_id, status=status,
                                finished=time.time(), summary=summary)
        log(f"spool: [{status}] {summary.splitlines()[0][:100]}")
    return len(entries)
