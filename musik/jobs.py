"""Job store for the Telegram bot worker (`musik bot`).

One JSON file under state/, guarded by a lock (bot handlers and the
worker thread both touch it). Jobs run strictly one at a time.
"""

import json
import os
import threading
import time
import uuid

from .paths import state_dir

_lock = threading.Lock()

# statuses: queued -> running -> done | error
MAX_REMEMBERED = 100


def _job_file() -> str:
    return os.path.join(state_dir(), "bot-jobs.json")


def load_jobs() -> list[dict]:
    try:
        with open(_job_file(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def _save(jobs: list[dict]) -> None:
    os.makedirs(state_dir(), exist_ok=True)
    tmp = _job_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(jobs[-MAX_REMEMBERED:], fh, ensure_ascii=False, indent=1)
    os.replace(tmp, _job_file())


def add_job(text: str, chat_id: int) -> dict:
    job = {
        "id": uuid.uuid4().hex[:8],
        "text": text,
        "chat_id": chat_id,
        "status": "queued",
        "created": time.time(),
        "started": None,
        "finished": None,
        "summary": "",
    }
    with _lock:
        jobs = load_jobs()
        jobs.append(job)
        _save(jobs)
    return job


def update_job(job_id: str, **fields) -> dict | None:
    with _lock:
        jobs = load_jobs()
        for job in jobs:
            if job["id"] == job_id:
                job.update(fields)
                _save(jobs)
                return job
    return None


def get_job(job_id: str) -> dict | None:
    for job in load_jobs():
        if job["id"] == job_id:
            return job
    return None


def queue_stats() -> dict:
    jobs = load_jobs()
    running = [j for j in jobs if j["status"] == "running"]
    queued = [j for j in jobs if j["status"] == "queued"]
    return {
        "queued": len(queued),
        "running": len(running),
        "running_job": running[0] if running else None,
        "next_job": queued[0] if queued else None,
        "recent": [
            j for j in reversed(jobs) if j["status"] in ("done", "error")
        ][:5],
    }
