# -*- coding: utf-8 -*-
"""Smoke test for configurable ingest roots (musik/ingest.py, Story 7.8).

Run:  python manual_tests/smoke_ingest_roots.py
Pure logic: beets config is set in-process, _ingest_one and the MG
layout healing are monkeypatched — no library, no network.

Covers: default root when the config key is absent (backward compat),
config list honored and normalized, ad-hoc --root override (exactly one
root, never auto-created), configured roots auto-created, iteration
order preserved.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp()

from musik import ingest as ingest_mod   # noqa: E402

from beets import config as beets_config   # noqa: E402


def set_roots(v) -> None:
    if v is None:
        try:
            del beets_config["musik"]["ingest"]["roots"]
        except Exception:
            pass
    else:
        beets_config["musik"]["ingest"]["roots"] = v


# 1) no config key -> default MG staging root (normpath'd)
set_roots(None)
roots = ingest_mod._configured_roots()
assert len(roots) == 1 and roots[0].endswith(os.sep + "musicgrabber"), roots
print("1) default root without config key OK:", roots[0])

# 2) config list honored, normalized, blanks dropped
set_roots(["/data/staging/mg ", "", "C:\\drop\\windows"])
roots = ingest_mod._configured_roots()
assert len(roots) == 2, roots
assert roots[0] == os.path.normpath("/data/staging/mg"), roots
assert roots[1] == os.path.normpath("C:\\drop\\windows"), roots
print("2) configured roots honored + normalized OK")

# 3) single string instead of list is tolerated
set_roots("/only/one")
roots = ingest_mod._configured_roots()
assert roots == [os.path.normpath("/only/one")], roots
print("3) single-string config tolerated OK")
set_roots(None)

# 4) cmd_ingest iteration: patched _ingest_one sees configured roots in
#    order; configured roots get created; ad-hoc --root is NOT created
seen = []


def fake_ingest_one(root: str) -> int:
    seen.append(root)
    return 0


def fake_layout() -> None:
    seen.append("<layout>")


ingest_mod._ingest_one = fake_ingest_one
from musik import musicgrabber as mg_mod   # noqa: E402

mg_mod.ensure_staging_layout = fake_layout

drop_a = os.path.join(tmp, "drop-a")
drop_b = os.path.join(tmp, "drop-b")
set_roots([drop_a, drop_b])
seen.clear()
assert ingest_mod.cmd_ingest() == 0
assert seen[:2] == [drop_a, drop_b] and seen[2] == "<layout>", seen
assert os.path.isdir(drop_a) and os.path.isdir(drop_b), "dropzones not created"
print("4) cmd_ingest iterates configured roots, creates dropzones OK")

adhoc = os.path.join(tmp, "ad-hoc", "sub")
seen.clear()
assert ingest_mod.cmd_ingest(root=adhoc) == 0
assert seen == [adhoc, "<layout>"], seen
assert not os.path.exists(os.path.join(tmp, "ad-hoc")), "ad-hoc root must not be auto-created"
print("5) ad-hoc --root: exactly one root, never auto-created OK")

shutil.rmtree(tmp, ignore_errors=True)
print("smoke_ingest_roots: all assertions passed")
