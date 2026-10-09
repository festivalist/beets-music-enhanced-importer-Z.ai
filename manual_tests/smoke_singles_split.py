# -*- coding: utf-8 -*-
"""Smoke test for the singles-tree split rule (musik/scan.py).

Run:  python manual_tests/smoke_singles_split.py
Pure logic: tag readers are monkeypatched, "files" are empty dummies —
no beets library, no network, temp-isolated.

Covers the Phase-5b leftover case (2026-10-09): the library's own
singleton layout puts several one-file releases (each carrying its TRUE
album tag) into one Singles/<Artist>/ directory. should_split's
multi-artist heuristics can never fire there, so scan now force-splits
any unit below the configured singleton root — unless the files share
one consistent album tag (a real album living under that name).
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp()

from musik import scan as scan_mod   # noqa: E402

# Fake per-file tags: {absolute path: {field: value}}
TAGS: dict[str, dict[str, str]] = {}


def fake_tag(f: str, field: str) -> str:
    return TAGS.get(os.path.normcase(f), {}).get(field, "")


scan_mod.tag_of = fake_tag
# dummies are 0-byte; make_unit must keep them as readable audio files
scan_mod.readable_file = lambda p: os.path.isfile(p)

_n = 0


def unit_for(rel: str, files: list[tuple[str, dict[str, str]]]) -> dict:
    """Build <fresh root>/<rel>/ with dummy files and classify that root."""
    global _n
    _n += 1
    root = os.path.join(tmp, f"root{_n}")
    d = os.path.join(root, *rel.split("/"))
    os.makedirs(d, exist_ok=True)
    for fname, tags in files:
        p = os.path.join(d, fname)
        open(p, "wb").close()
        TAGS[os.path.normcase(p)] = tags
    units, _notes = scan_mod.classify(root)
    match = [u for u in units
             if os.path.normcase(u["path"]) == os.path.normcase(d)]
    assert match, f"no unit for {rel}: {[u['path'] for u in units]}"
    return match[0]


def beets_singleton_template(t: str) -> None:
    from beets import config as beets_config

    beets_config["paths"]["singleton"] = t


# 1) template parsing: literal first component, both separators,
#    variable-first template disables the rule
beets_singleton_template("Singles/$artist/$year - $title%aunique{}")
assert scan_mod.singleton_root() == "Singles", scan_mod.singleton_root()
beets_singleton_template("Singles\\$artist\\x")
assert scan_mod.singleton_root() == "Singles", scan_mod.singleton_root()
beets_singleton_template("$artist/$title")
assert scan_mod.singleton_root() == "", scan_mod.singleton_root()
beets_singleton_template("")
assert scan_mod.singleton_root() == "", scan_mod.singleton_root()
print("1) singleton_root() template parsing OK")

beets_singleton_template("Singles/$artist/$year - $title%aunique{}")

# 2) singles tree: one artist, several files, each its own true album
#    -> force split into singletons (the 77-file Phase-5b leftover shape)
u = unit_for("Singles/Falco", [
    ("1985 - Jeanny.mp3", {"artist": "Falco", "album": "Falco 3",
                           "title": "Jeanny"}),
    ("1982 - Der Kommissar.mp3", {"artist": "Falco", "album": "Einzelhaft",
                                  "title": "Der Kommissar"}),
    ("1985 - Rock Me Amadeus.mp3", {"artist": "Falco", "album": "Falco 3",
                                    "title": "Rock Me Amadeus"}),
])
assert u["split_into_singletons"] is True, u
assert "singles-tree" in u["hints"], u
print("2) Singles/<Artist>/ with per-file true albums -> split OK")

# 3) same tree but ONE consistent album tag -> real album, stays whole
u = unit_for("Singles/VA Gold", [
    ("01.mp3", {"artist": "A One", "album": "Singles Gold", "title": "T1"}),
    ("02.mp3", {"artist": "B Two", "album": "singles gold", "title": "T2"}),
])
assert not u["split_into_singletons"], u
assert "singles-tree" not in u["hints"], u
print("3) consistent album tag under Singles/ -> album stays whole OK")

# 4) ordinary album dir outside the singles tree -> untouched
u = unit_for("Regular Band/2020 - LP", [
    ("01.mp3", {"artist": "Regular Band", "album": "LP", "title": "T1"}),
    ("02.mp3", {"artist": "Regular Band", "album": "LP", "title": "T2"}),
])
assert not u["split_into_singletons"], u
assert "singles-tree" not in u["hints"], u
print("4) regular album dir -> untouched OK")

# 5) deep nesting: the rule fires wherever the root name appears as a
#    path component (migration staging mirrors the library tree)
u = unit_for("_incoming/win-lib/Singles/Ken@Work", [
    ("2024 - Here We Go.mp3", {"artist": "Ken@Work", "album": "Here We Go",
                               "title": "Here We Go"}),
    ("2024 - The Guarantee.mp3", {"artist": "Ken@Work",
                                  "album": "The Guarantee",
                                  "title": "The Guarantee"}),
])
assert u["split_into_singletons"] is True, u
print("5) mirrored singles tree inside staging -> split OK")

print("smoke_singles_split: all assertions passed")
