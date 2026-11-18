# -*- coding: utf-8 -*-
"""Smoke test für Story 3.3 (Track-Upgrades lossy → besser).

Run:  python manual_tests/smoke_upgrades.py
Netzfrei: beets-Lib und MusicGrabber sind Fakes; der Batch-Executor
bekommt lock_runner/ingest_fn injiziert. Deckt: Scanner (Schwelle,
Format-Filter, Junk-Ausnahme, Sortierung), Batch-Planung (Größe,
Behalten ausgenommen), Entscheidungen (persistieren über Rescan),
Batch-Flow (replaced / kept / no-source / dup_risk / kept-user),
ingest-pending-Wiederaufnahme ohne Re-Download, bot_http-Aktionen
(Validierung + Enqueue) und Snapshot-Summary.
"""

import json
import os
import sys
import tempfile

# Windows-Konsolen sind oft cp1252 — Emoji in den Summary-Zeilen dürfen
# den Lauf nicht killen (dasselbe Reconfigure wie cli.main; die Suite
# setzt zusätzlich PYTHONUTF8=1, direkte Läufe hier ohne Env).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import musik.bot_http as BH  # noqa: E402
import musik.paths as paths_mod  # noqa: E402
import musik.upgrades as U  # noqa: E402


class It:
    """Beets-Item-Ersatz mit genau den Attributen, die upgrades liest."""

    def __init__(self, iid, artist, title, fmt, kbps, length=200.0,
                 album="Alb", track=1):
        self.id = iid
        self.artist = artist
        self.title = title
        self.format = fmt
        self.bitrate = kbps * 1000
        self.length = length
        self.album = album
        self.track = track
        self.albumartist = artist
        self.path = os.path.join("C:\\lib", artist, f"{title}.{fmt.lower()}")


class Lib:
    def __init__(self, items):
        self._items = items

    def items(self):
        return list(self._items)


class FakeMG:
    """MG-Ersatz: liefert je Query einen FLAC-Treffer — außer für Queries
    mit 'NoSrc' (keine Ergebnisse) oder 'DownFail' (Jobs failen)."""

    def __init__(self, download_fail=False):
        self.queries = []
        self.download_fail = download_fail

    def mg_config(self):
        return {"enabled": True}

    def available(self):
        return True

    def ensure_staging_layout(self):
        pass

    def search(self, q, limit=10):
        self.queries.append(q)
        if "NoSrc" in q:
            return "tok", []
        artist, title = q.split(" - ", 1)
        return "tok", [{
            "video_id": "v1", "title": title, "artist": artist,
            "source": "testflac", "source_url": "",
            "quality": "FLAC 1000 kbps", "quality_tier": 6,
            "relevance": 10, "duration_secs": 200, "is_playlist": False,
        }]

    def ranked_results(self, q, results):
        return [r for r in results if r["video_id"]]

    def download(self, result, search_token=""):
        if self.download_fail:
            raise RuntimeError("job failed")
        return "job-1"

    def wait_for_job(self, job_id, timeout=None, progress=None):
        if self.download_fail:
            raise RuntimeError("job failed")
        return {"status": "completed"}


def _patch_paths(sd, rd):
    paths_mod.state_dir = lambda: sd
    paths_mod.reports_dir = lambda: rd
    U.state_dir = lambda: sd      # Modul-Bindung in upgrades.py
    U.reports_dir = lambda: rd
    U._FMT_TIER = {}              # Tier-Cache zurücksetzen (lazy reload)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        sd = os.path.join(tmp, "state")
        rd = os.path.join(tmp, "reports")
        os.makedirs(sd, exist_ok=True)
        os.makedirs(rd, exist_ok=True)
        _patch_paths(sd, rd)

        # -- 1) Scanner: Schwelle, Format-Filter, Junk, Sortierung --------
        lib1 = Lib([
            It(1, "LoArt", "LoTitle", "MP3", 128, 200.0),
            It(2, "OkArt", "OkTitle", "MP3", 320, 200.0),     # über Schwelle
            It(3, "LossArt", "LossTitle", "FLAC", 900, 200.0),  # lossless
            It(4, "", "JunkTitle", "MP3", 96, 200.0),          # Junk: Artist
            It(5, "JunkArt", "", "AAC", 96, 200.0),            # Junk: Title
            It(6, "ZeroArt", "ZeroTitle", "Opus", 0, 200.0),   # Bitrate 0
            It(7, "AArt", "ATitle", "AAC", 130, 180.0),
            It(8, "Dup", "DupTitle", "MP3", 160, 200.0),
        ])
        cands, meta = U.scan_candidates(lib1, threshold_kbps=200)
        ids = [c["id"] for c in cands]
        assert ids == [1, 7, 8], ids  # 128k < 130k < 160k: schlechteste zuerst
        assert meta["junk"] == 2, meta
        assert cands[0]["kbps"] == 128 and cands[0]["format"] == "MP3"

        # -- 2) Scan + Plan: Batches nach Größe, Report da -----------------
        lines, failed = U.cmd_scan(lib=lib1)
        assert failed == 0, lines
        st = U.load()
        assert len(st["candidates"]) == 3 and st["threshold_kbps"] == 200
        assert st["batch_size"] == U.DEFAULTS["batch_size"]
        assert [b["n"] for b in st["batches"]] == [3], st["batches"]
        bid = st["batches"][0]["id"]
        assert bid.startswith("upg-") and bid.endswith("b001"), bid
        report = os.path.join(rd, "upgrade-report.md")
        assert os.path.isfile(report), report
        with open(report, encoding="utf-8") as fh:
            rtext = fh.read()
        assert "LoArt" in rtext and "JunkArt" not in rtext, "Report-Inhalt"

        # -- 3) Behalten-Entscheidung: Batch-Planung nimmt sie aus,
        #      Rescan erhält sie -------------------------------------------------
        lines, failed = U.cmd_decide([7], "keep")
        assert failed == 0, lines
        st = U.load()
        kept_c = next(c for c in st["candidates"] if c["id"] == 7)
        assert kept_c["decision"] == "keep"
        U.plan(st)
        assert all(7 not in [c["id"] for c in b["items"]]
                   for b in st["batches"]), "keep im Batch"
        lines, failed = U.cmd_scan(lib=lib1)  # Rescan
        st = U.load()
        kept_c = next(c for c in st["candidates"] if c["id"] == 7)
        assert kept_c["decision"] == "keep", "Entscheidung überlebt Rescan"
        bid = st["batches"][0]["id"]

        # -- 4) bot_http-Aktionen: Validierung + Enqueue (kein HTTP nötig,
        #      der Server-Pfad ist in smoke_bot_http abgedeckt). Der Decide-
        #      Executor läuft ECHT (schreibt nur upgrades.json); der Scan-
        #      Executor würde die echte Lib öffnen → nur Enqueue prüfen. ---
        import musik.bot as B

        captured: dict = {}

        def fake_enqueue(text, **fields):
            captured.clear()
            captured.update(fields)
            captured["text"] = text
            return 200, {"queued": "j1"}

        BH._enqueue_job = fake_enqueue
        code, out = BH.handle_action({"action": "upgrade_batch",
                                      "batch_id": "upg-unbekannt"})
        assert code == 400 and "unbekannter Batch" in out["error"], (code, out)
        code, out = BH.handle_action({"action": "upgrade_batch",
                                      "batch_id": bid})
        assert code == 200 and captured["kind"] == "upgrade_batch", (code, out)
        code, out = BH.handle_action({"action": "upgrade_decide",
                                      "item_ids": [999]})
        assert code == 400, (code, out)
        code, out = BH.handle_action({"action": "upgrade_decide",
                                      "item_ids": [1, 8],
                                      "decision": "keep"})
        assert code == 200 and captured["kind"] == "upgrade_decide", \
            (code, out)
        B._execute_upgrade_decide({"id": "j1", "chat_id": 0, **captured},
                                  lambda s: None)
        code, out = BH.handle_action({"action": "upgrade_decide",
                                      "item_ids": [1], "decision": "quatsch"})
        assert code == 400, (code, out)
        code, out = BH.handle_action({"action": "upgrade_scan"})
        assert code == 200 and captured["kind"] == "upgrade_scan", (code, out)
        st = U.load()
        kept_now = [c["id"] for c in st["candidates"]
                    if c["decision"] == "keep"]
        assert sorted(kept_now) == [1, 7, 8], kept_now
        # wieder freigeben (None)
        code, out = BH.handle_action({"action": "upgrade_decide",
                                      "item_ids": [1, 8], "decision": None})
        assert code == 200, (code, out)
        B._execute_upgrade_decide({"id": "j1", "chat_id": 0, **captured},
                                  lambda s: None)
        st = U.load()
        assert not any(c.get("decision") for c in st["candidates"]
                       if c["id"] in (1, 8))

        # frischer Plan mit allen 3 frei; dann Behalten NACH der Planung —
        # genau der Pfad, den ein Klick im offenen Batch nimmt (kept-user)
        U.cmd_decide([7], None)   # 7 aus dem Rescan-Reservoier freigeben
        U.cmd_scan(lib=lib1)
        st = U.load()
        bid = st["batches"][0]["id"]
        assert [c["id"] for c in st["batches"][0]["items"]] == [1, 7, 8]
        U.cmd_decide([7], "keep")

        # -- 5) Snapshot-Summary + detail -----------------------------------
        s = U.summary()
        assert s["total"] == 3 and s["kept"] == 1 and s["batches"], s
        assert "candidates" not in s, "Summary muss leicht bleiben"
        d = U.detail()
        assert len(d["candidates"]) == 3, d

        # -- 6) Batch-Flow: replaced / kept-user / no-source / dup_risk -----
        # Bibliothek NACH dem Import: Kandidat 1 ersetzt (FLAC), 8 doppelt,
        # 7 unverändert (kept-user läuft sowieso nicht in den Download)
        lib2 = Lib([
            It(100, "LoArt", "LoTitle", "FLAC", 900, 200.0),   # ersetzt
            It(101, "Dup", "DupTitle", "MP3", 160, 200.0),
            It(102, "Dup", "DupTitle", "MP3", 160, 201.0),     # Dup-Risk
            It(103, "AArt", "ATitle", "AAC", 130, 180.0),      # unverändert
        ])
        mg = FakeMG()  # "Dup" würde auch liefern — der Batch Match zählt
        ingests = []
        progress_log = []

        def lock_runner(fn, patience=0.0):
            ingests.append(fn)
            fn()
            return True

        lines, failed = U.cmd_batch(
            bid, progress=lambda l, i, t: progress_log.append(l),
            lock_runner=lock_runner, mg_mod=mg, ingest_fn=lambda: None,
            lib=lib2)
        assert failed == 0, lines
        st = U.load()
        b = next(x for x in st["batches"] if x["id"] == bid)
        assert b["status"] == "done", b
        res = b["results"]
        assert res["replaced"] == 1, res        # 1 → FLAC in lib2
        assert res["no_source"] == 0, res       # alle drei liefern
        assert len(res.get("dup_risk", [])) == 1, res  # 8 → 2 Kopien
        assert res["kept"] == 1, res            # 7 kept-user
        c1 = next(c for c in b["items"] if c["id"] == 1)
        assert c1["status"] == "downloaded" and c1["source"] == "testflac"
        c7 = next(c for c in b["items"] if c["id"] == 7)
        assert c7["status"] == "kept-user", c7
        assert len(ingests) == 1, "ein Ingest für den Batch"
        assert any("ersetzt" in l for l in lines), lines
        assert progress_log, "Progress gefeuert"

        # -- 7) kept-Batch nochmal anstoßen: nichts mehr zu holen ----------
        code, out = BH.handle_action({"action": "upgrade_batch",
                                      "batch_id": bid})
        assert code == 400 and "nicht anstoßbar" in out["error"], (code, out)

        # -- 8) ingest-pending: Download-Phase übersprungen -----------------
        def queued_batch():
            stx = U.load()
            qs = [b for b in stx["batches"] if b["status"] == "queued"]
            assert qs, "kein queued Batch im Plan"
            return qs[0]

        lines, failed = U.cmd_scan(lib=lib1)
        b2 = queued_batch()
        bid2 = b2["id"]
        st = U.load()
        b2 = next(x for x in st["batches"] if x["id"] == bid2)
        b2["status"] = "ingest-pending"
        for c in b2["items"]:
            c["status"] = "downloaded"
            c["source"] = "testflac"
        U.save(st)
        mg2 = FakeMG()
        ingests.clear()
        lines, failed = U.cmd_batch(bid2, lock_runner=lock_runner,
                                    mg_mod=mg2, ingest_fn=lambda: None,
                                    lib=lib2)
        assert failed == 0, lines
        assert mg2.queries == [], "kein Re-Download bei ingest-pending"
        assert len(ingests) == 1, "Ingest nachgeholt"
        st = U.load()
        b2 = next(x for x in st["batches"] if x["id"] == bid2)
        assert b2["status"] == "done", b2

        # -- 9) no-source als dokumentiertes Ergebnis -----------------------
        lines, failed = U.cmd_scan(lib=Lib([It(5, "NoSrc Art", "NoSrc Title",
                                               "MP3", 96, 200.0)]))
        bid3 = queued_batch()["id"]
        mg3 = FakeMG()
        lines, failed = U.cmd_batch(bid3, lock_runner=lock_runner,
                                    mg_mod=mg3, ingest_fn=lambda: None,
                                    lib=Lib([]))
        assert failed == 0, lines
        st = U.load()
        b3 = next(x for x in st["batches"] if x["id"] == bid3)
        assert b3["results"]["no_source"] == 1, b3["results"]
        assert "ohne Quelle" in "\n".join(lines), lines

        # -- 10) MG nicht erreichbar: Batch bricht sauber, nichts geändert --
        lines, failed = U.cmd_scan(lib=Lib([It(9, "XArt", "XTitle", "MP3",
                                               128, 200.0)]))
        bid4 = queued_batch()["id"]

        class DownMG(FakeMG):
            def available(self):
                return False

        lines, failed = U.cmd_batch(bid4, lock_runner=lock_runner,
                                    mg_mod=DownMG(), ingest_fn=lambda: None)
        assert failed == 1, lines
        assert any("nicht gestartet" in l for l in lines), lines
        st = U.load()
        b4 = next(x for x in st["batches"] if x["id"] == bid4)
        assert b4["status"] == "error", b4
        assert all(i.get("status") in (None, "queued")
                   for i in b4["items"]), "kein Track angefasst"

        # -- 11) Token-Overlap (Fuzzy-Match-Regel) --------------------------
        assert U._token_overlap("Wonderwall (live at Knebworth Park)",
                                "Wonderwall")
        assert not U._token_overlap("Wonderwall", "Champagne Supernova")

    print("smoke_upgrades: alle Assertionen grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
