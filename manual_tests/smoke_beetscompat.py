# -*- coding: utf-8 -*-
"""Smoke test für die beets-Versionsbrücke (Story 9.11).

tag_album_compat muss autotag.tag_album in BEIDEN API-Formen korrekt
rufen und versionstolerant die Proposal liefern:
- beets 2.13: tag_album(Item-Liste, …) → (artist, album, Proposal)
- beets 2.14: tag_album(Source.from_items(…), …) → Proposal

Sektion 2 (injiziertes Fake-Modul) läuft auf beiden Versionen und
prüft den Shim-Vertrag; Sektion 1 nur auf 2.13 (Windows-Dev),
Sektion 3 nur auf 2.14 (Pi) gegen ECHTE Source-Objekte und Items.
Kein Netzwerk.

Run:  python manual_tests/smoke_beetscompat.py
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import beets.autotag  # noqa: E402

from musik.beetscompat import tag_album_compat  # noqa: E402

try:
    from beets.autotag.source import Source as RealSource
except ImportError:
    RealSource = None


class _Proposal:
    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.candidates: list = []


class _Source:
    def __init__(self, items) -> None:
        self.items = list(items)

    @classmethod
    def from_items(cls, items):
        return cls(items)


def main() -> int:
    items = [{"tag": "i1"}, {"tag": "i2"}]
    p213, p214 = _Proposal("2.13"), _Proposal("2.14")
    orig_tag_album = beets.autotag.tag_album
    orig_source_mod = sys.modules.get("beets.autotag.source")

    def restore():
        beets.autotag.tag_album = orig_tag_album
        if orig_source_mod is None:
            sys.modules.pop("beets.autotag.source", None)
        else:
            sys.modules["beets.autotag.source"] = orig_source_mod

    # --- 1) 2.13-Simulation (nur dort, wo es kein echtes Source gibt):
    #        Item-LISTE rein, 3-Tupel zurück, Proposal raus
    if RealSource is None:
        def tag_213(items_arg, search_artist=None, search_name=None,
                    search_ids=None):
            assert isinstance(items_arg, list), \
                f"2.13 erwartet Liste, bekommen {type(items_arg)}"
            assert items_arg == items, items_arg
            assert search_artist == "A" and search_name == "B", \
                (search_artist, search_name)
            assert search_ids == ["id-1"], search_ids
            return ("A", "B", p213)

        beets.autotag.tag_album = tag_213
        try:
            out = tag_album_compat(items, search_artist="A", search_name="B",
                                   search_ids=["id-1"])
            assert out is p213, out
        finally:
            restore()
        print("1) 2.13-Form: Item-Liste rein, 3-Tupel entpackt OK")

    # --- 2) 2.14-Vertrag über injiziertes Fake-Modul (läuft auf beiden):
    #        Source-Konstrukt rein, Proposal direkt raus
    fake_mod = types.ModuleType("beets.autotag.source")
    fake_mod.Source = _Source
    sys.modules["beets.autotag.source"] = fake_mod

    def tag_214(source_arg, search_artist=None, search_name=None,
                search_ids=None):
        assert isinstance(source_arg, _Source), \
            f"2.14 erwartet Source, bekommen {type(source_arg)}"
        assert source_arg.items == list(items), source_arg.items
        assert search_artist == "A" and search_name == "B", \
            (search_artist, search_name)
        assert search_ids == ["id-1"], search_ids
        return p214

    beets.autotag.tag_album = tag_214
    try:
        out = tag_album_compat(items, search_artist="A", search_name="B",
                               search_ids=["id-1"])
        assert out is p214, out
    finally:
        restore()
    print("2) 2.14-Form (Fake): Source rein, Proposal direkt OK")

    # --- 3) 2.14 echt (nur Pi): ECHTES Source-Modul + echte beets-Items;
    #        das ist exakt der Zweig, der 2026-10-21 crashte
    if RealSource is not None:
        from beets.library import Item
        real_items = [Item(albumartist="A", artist="A", album="B",
                           mb_albumid="") for _ in range(2)]
        seen = {}

        def tag_real(source_arg, search_artist=None, search_name=None,
                     search_ids=None):
            seen["src"] = source_arg
            return p214

        beets.autotag.tag_album = tag_real
        try:
            out = tag_album_compat(real_items)
            assert out is p214, out
            assert isinstance(seen["src"], RealSource), seen
            assert len(seen["src"].items) == 2, seen
            assert seen["src"].artist == "A" and seen["src"].name == "B", \
                seen["src"]
        finally:
            restore()
        print("3) 2.14 echt: Source.from_items mit echten Items OK "
              f"(desc={seen['src'].desc!r})")

    print("smoke_beetscompat: alle Assertionen grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
