# -*- coding: utf-8 -*-
"""Smoke test for boot-time job recovery (Story 11.6).

Run:  python manual_tests/smoke_job_watchdog.py
The bot queue is in-memory only, so after a restart every 'running'
record is a zombie (its thread is gone) and 'queued' records would be
silently lost. Checks: zombies become error with an honest summary,
queued jobs survive in file order for re-enqueue, done jobs are
untouched, and the restart notice lists the killed job texts (with the
"+N weitere" overflow).
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from musik import jobs as J  # noqa: E402
import musik.bot as B  # noqa: E402


def seed(base: str, jobs: list) -> str:
    sd = os.path.join(base, "state")
    os.makedirs(sd, exist_ok=True)
    with open(os.path.join(sd, "bot-jobs.json"), "w", encoding="utf-8") as fh:
        json.dump(jobs, fh, ensure_ascii=False)
    return sd


def job(jid: str, status: str, text: str = "q", chat_id: int = 1) -> dict:
    return {"id": jid, "text": text, "chat_id": chat_id, "status": status,
            "created": 1000.0, "started": None, "finished": None,
            "summary": ""}


def case1_mixed_store():
    base = tempfile.mkdtemp(prefix="smoke-jw-")
    seed(base, [
        job("done1", "done", "old link"),
        job("run1", "running", "https://music.youtube.com/playlist?list=X"),
        job("q1", "queued", "https://open.spotify.com/track/1"),
        job("run2", "running", "free text search"),
        job("q2", "queued", "https://music.youtube.com/watch?v=y"),
    ])
    J.state_dir = lambda: os.path.join(base, "state")  # type: ignore
    killed, requeued = J.recover_interrupted()
    assert [j["id"] for j in killed] == ["run1", "run2"], killed
    assert [j["id"] for j in requeued] == ["q1", "q2"], requeued
    stored = {j["id"]: j for j in J.load_jobs()}
    for jid in ("run1", "run2"):
        assert stored[jid]["status"] == "error", stored[jid]
        assert "Neustart" in stored[jid]["summary"], stored[jid]
        assert stored[jid]["finished"], stored[jid]
    assert stored["q1"]["status"] == "queued"
    assert stored["done1"]["status"] == "done"
    assert stored["done1"]["summary"] == ""
    print("1) mixed store: running->error, queued kept in order, done untouched OK")


def case2_empty_store():
    base = tempfile.mkdtemp(prefix="smoke-jw-")
    seed(base, [])
    J.state_dir = lambda: os.path.join(base, "state")  # type: ignore
    killed, requeued = J.recover_interrupted()
    assert killed == [] and requeued == []
    print("2) empty store: no-op OK")


def case3_notice_formatting():
    msgs = [f"link {i}" for i in range(7)]
    notice = B._restart_notice(msgs)
    assert "7 Job(s)" in notice
    assert "• link 0" in notice and "• link 4" in notice
    assert "link 5" not in notice, "only first 5 listed"
    assert "+2 weitere" in notice
    single = B._restart_notice(["only one"])
    assert "1 Job(s)" in single and "weitere" not in single
    print("3) restart notice: list + overflow + single OK")


if __name__ == "__main__":
    case1_mixed_store()
    case2_empty_store()
    case3_notice_formatting()
    print("smoke_job_watchdog: alle Assertionen grün")
