"""Run state: which units exist and what happened to them.

state.json is the crash-safe source of truth for resumable runs. It is
written atomically after every unit.
"""

import json
import os
import tempfile
import time

from . import paths

STATUSES = (
    "pending",      # scanned, not yet attempted
    "auto",         # auto-accepted and imported
    "review",       # low confidence; waiting in review.csv for a decision
    "unmatched",    # lookups answered, nothing found; left in place
    "network",      # lookup failed (rate limit / network); retry candidate
    "duplicate",    # lost a quality comparison; source moved to _trash
    "ignored",      # excluded by user decision (apply command)
    "error",        # unexpected processing error; see reason
)


def state_file() -> str:
    return os.path.join(paths.state_dir(), "state.json")


def load() -> dict:
    f = state_file()
    if os.path.isfile(f):
        with open(f, encoding="utf-8") as fh:
            return json.load(fh)
    return {"meta": {"created": time.time()}, "units": {}}


def save(state: dict) -> None:
    d = paths.state_dir()
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1, ensure_ascii=False)
        os.replace(tmp, state_file())
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def units(state: dict) -> dict:
    return state.setdefault("units", {})


def get_unit(state: dict, path: str) -> dict | None:
    return units(state).get(os.path.normcase(os.path.normpath(path)))


def put_unit(state: dict, unit: dict) -> None:
    units(state)[os.path.normcase(os.path.normpath(unit["path"]))] = unit


def set_status(unit: dict, status: str, reason: str = "") -> None:
    unit["status"] = status
    unit["reason"] = reason
    unit["updated"] = time.time()


def counts(state: dict) -> dict:
    out: dict[str, int] = {}
    for u in units(state).values():
        out[u.get("status", "pending")] = out.get(u.get("status", "pending"), 0) + 1
    return out
