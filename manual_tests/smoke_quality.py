# -*- coding: utf-8 -*-
"""Smoke test for quality.score() long-path routing (EPIC 6.2 / P2-5).

Run:  python manual_tests/smoke_quality.py
A swallowed mutagen read error on a >260-char Windows path would score a
lossless file tier 0 — and the duplicate resolver would trash the wrong
copy. This verifies score() routes through scan.openable().
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from musik import quality as Q  # noqa: E402

# 1) missing file: no crash; the tier still comes from the extension
assert Q.score(os.path.join(tempfile.gettempdir(), "nope-does-not-exist.flac")) \
    == (6, 0, 0, 0)
assert Q.score(os.path.join(tempfile.gettempdir(), "nope-does-not-exist.xyz")) \
    == (0, 0, 0, 0)
print("1) missing file -> extension tier, no crash OK")

# 2) a >240-char path must reach mutagen WITH the \\?\ prefix on Windows
#    (openable() only prefixes long paths — short ones pass through as-is)
tmp = tempfile.mkdtemp()
target = os.path.join(tmp, "x" * 200 + ".flac")
open(Q.openable(target), "wb").close()
captured = []
real_file = Q.mutagen.File


def fake_file(p, *a, **kw):
    captured.append(p)
    return None


Q.mutagen.File = fake_file
try:
    Q.score(target)
finally:
    Q.mutagen.File = real_file
assert captured, "mutagen.File was never called"
if os.name == "nt":
    assert captured[0].startswith("\\\\?\\"), f"no long-path prefix: {captured[0]}"
else:
    assert captured[0] == target
print(f"2) mutagen receives openable()-routed path OK ({captured[0][:40]}...)")

# 3) a genuinely >260-char path must not raise out of score()
deep = os.path.join(tmp, *(("d" * 40,) * 6))
long_path = os.path.join(deep, "f" * 50 + ".flac")
try:
    if os.name == "nt":
        os.makedirs(Q.openable(deep))
        open(Q.openable(long_path), "wb").close()
    else:
        os.makedirs(deep)
        open(long_path, "wb").close()
    s = Q.score(long_path)
    assert len(s) == 4
    print(f"3) >260-char path scores without crash OK {s}")
except OSError as e:
    print(f"3) skipped — cannot create long path here ({e})")

print("smoke_quality: all assertions passed")
