# -*- coding: utf-8 -*-
"""Smoke test für Story 3.3 (Track-Upgrades lossy → besser).

Run:  python manual_tests/smoke_upgrades.py
Netzfrei: beets-Lib, MusicGrabber, Scan/Asis/Ingest sind Fakes; der
Batch-Executor bekommt lock_runner/scan_fn/asis_fn/ingest_fn injiziert
und der Identitäts-Gate (Dauer/Fingerprint/Stamp) wird an den Nahtstellen
gepatcht. Deckt: Scanner (Schwelle, Format-Filter, Junk-Ausnahme,
Sortierung), Batch-Planung (Größe, Behalten ausgenommen), Entscheidungen
(persistieren über Rescan), Batch-Flow (replaced / kept-user / namesake /
staged → partial → Wiederaufnahme / no-source / gone), Lock-Verweigerung
(ingest-pending, kein Re-Download), MG-Ausfall (kein Track berührt),
Gate-Einzellogik (Dauer ±5 s, Fingerprint-Schwelle, fehlende Alt-Datei)
und bot_http-Aktionen (Validierung + Enqueue + Executor).
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

import musik.bot as B  # noqa: E402
import musik.bot_http as BH  # noqa: E402
import musik.paths as paths_mod  # noqa: E402
import musik.state as state_mod  # noqa: E402
import musik.trash as trash_mod  # noqa: E402
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
    """MG-Ersatz: legt je Download eine echte Staging-Datei an (der Gate/
    Isolate/Scan-Flow braucht reale Pfade) — außer für Queries mit 'NoSrc'
    (keine Ergebnisse)."""

    def __init__(self, inc, fail_names=()):
        self.inc = inc
        self.queries = []
        self.fail_names = set(fail_names)

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
        folder = os.path.join(self.inc, "musicgrabber", "Singles",
                              result["artist"] or "Unknown")
        os.makedirs(folder, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in " -_'&()!.+" else "_"
                       for c in result["title"])
        path = os.path.join(folder, f"{safe}.m4a")
        with open(path, "wb") as fh:
            fh.write(b"\x00")
        return "job-1"

    def wait_for_job(self, job_id, timeout=None, progress=None):
        return {"status": "completed"}


def _patch_paths(sd, rd, inc):
    paths_mod.state_dir = lambda: sd
    paths_mod.reports_dir = lambda: rd
    paths_mod.incoming_dir = lambda: inc
    U.state_dir = lambda: sd      # Modul-Bindung in upgrades.py
    U.reports_dir = lambda: rd
    U._FMT_TIER = {}              # Tier-Cache zurücksetzen (lazy reload)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        sd = os.path.join(tmp, "state")
        rd = os.path.join(tmp, "reports")
        inc = os.path.join(tmp, "incoming")
        for d in (sd, rd, inc):
            os.makedirs(d, exist_ok=True)
        _patch_paths(sd, rd, inc)
        trash_calls: list = []
        trash_mod.trash_files = lambda files, reason, detail="": \
            trash_calls.append((tuple(files), reason))
        gate_calls: list = []
        real_gate = U._gate_file   # Original sichern (Sektion 12 restauriert)

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
            assert "LoArt" in fh.read() and "JunkArt" not in fh.read()

        # -- 3) Behalten-Entscheidung: Rescan erhält sie --------------------
        lines, failed = U.cmd_decide([7], "keep")
        assert failed == 0, lines
        st = U.load()
        assert next(c for c in st["candidates"]
                    if c["id"] == 7)["decision"] == "keep"
        U.plan(st)
        assert all(7 not in [c["id"] for c in b["items"]]
                   for b in st["batches"]), "keep im Batch"
        lines, failed = U.cmd_scan(lib=lib1)  # Rescan
        st = U.load()
        assert next(c for c in st["candidates"]
                    if c["id"] == 7)["decision"] == "keep", "überlebt Rescan"
        bid = next(b["id"] for b in st["batches"] if b["status"] == "queued")

        # -- 4) bot_http-Aktionen: Validierung + Enqueue; Decide-Executor ---
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
        assert sorted(c["id"] for c in st["candidates"]
                      if c["decision"] == "keep") == [1, 7, 8], st["candidates"]
        code, out = BH.handle_action({"action": "upgrade_decide",
                                      "item_ids": [1, 8, 7], "decision": None})
        assert code == 200, (code, out)
        B._execute_upgrade_decide({"id": "j1", "chat_id": 0, **captured},
                                  lambda s: None)
        st = U.load()
        assert not any(c.get("decision") for c in st["candidates"])

        # frischer Plan mit allen 3 frei; dann Behalten NACH der Planung
        # (kept-user-Pfad) + Freigabe von 7 für den Gate-Test unten
        U.cmd_scan(lib=lib1)
        st = U.load()
        bid = next(b["id"] for b in st["batches"] if b["status"] == "queued")
        assert [c["id"] for c in
                next(b for b in st["batches"]
                     if b["status"] == "queued")["items"]] == [1, 7, 8]
        U.cmd_decide([7], "keep")   # Entscheidung NACH der Planung

        # -- 5) Snapshot-Summary + detail -----------------------------------
        s = U.summary()
        assert s["total"] == 3 and s["kept"] == 1 and s["batches"], s
        assert "candidates" not in s, "Summary muss leicht bleiben"
        assert len(U.detail()["candidates"]) == 3

        # -- 6) Batch-Flow mit Gate: replaced / kept-user / namesake /
        #       staged → partial --------------------------------------------
        mg = FakeMG(inc)
        ingests, scans, asis_runs = [], [], []

        def lock_ok(fn, patience=0.0):
            fn()
            return True

        def fake_scan(root):
            scans.append(root)
            stx = U.load()
            for u in state_mod.units(stx).values():
                for f in (u.get("files") or []):
                    if os.path.isfile(f):
                        break
            # Einheiten je bereitliegender Staging-Datei registrieren
            for dirpath, _d, files in os.walk(
                    os.path.join(inc, "musicgrabber", "Singles")):
                audio = [os.path.join(dirpath, f) for f in files
                         if f.endswith(".m4a")]
                if audio:
                    state_mod.put_unit(stx, {
                        "path": dirpath, "status": "pending",
                        "reason": "", "updated": 1.0, "files": audio,
                        "singleton": True, "import_path": dirpath,
                    })
            state_mod.save(stx)

        def fake_asis(unit_paths, progress=None):
            asis_runs.append(list(unit_paths))
            stx = state_mod.load()
            for up in unit_paths:
                u = state_mod.get_unit(stx, up)
                if not u:
                    continue
                if "LoArt" in (u.get("path") or ""):
                    for f in (u.get("files") or []):
                        if os.path.isfile(f):
                            os.remove(f)  # simuliert Import (Datei weg)
                    u["status"] = "asis"
            state_mod.save(stx)
            return ["✅ fake import"], False

        def fake_gate(path, cand):
            gate_calls.append(cand["id"])
            if cand["artist"] == "Dup":
                return "namesake", "Test-Namensvetter"
            return "ready", ""

        U._gate_file = fake_gate

        def fake_ingest():
            ingests.append(1)

        lines, failed = U.cmd_batch(
            bid, progress=lambda l, i, t: None, lock_runner=lock_ok,
            mg_mod=mg, scan_fn=fake_scan, asis_fn=fake_asis,
            ingest_fn=fake_ingest, lib=Lib([
                It(100, "LoArt", "LoTitle", "FLAC", 900, 200.0)]))
        assert failed == 0, lines
        st = U.load()
        b = next(x for x in st["batches"] if x["id"] == bid)
        res = b["results"]
        assert res["replaced"] == 1, res           # 1 → FLAC in der Fake-Lib
        assert res["namesake"] == 1, res           # 8 → Gate verwirft
        assert res["kept_user"] == 1, res          # 7 → Behalten nach Planung
        assert res["staged"] == 0, res             # 8s Datei wurde getrasht,
        # 1s Datei vom Fake-Import entfernt → keine Reststände
        assert b["status"] == "done", b["status"]
        assert any("Namensvetter" in l for l in lines), lines
        assert gate_calls == [1, 8], gate_calls    # 7 wurde nie geladen
        assert len(ingests) == 1 and len(scans) == 1, (ingests, scans)
        assert len(asis_runs) == 1, asis_runs
        assert any(tr[1] == "upgrade-namesake" for tr in trash_calls), \
            trash_calls
        c1 = next(c for c in b["items"] if c["id"] == 1)
        assert c1["status"] == "ready" and c1["staged_path"], c1
        assert not os.path.isfile(c1["staged_path"]), "Import entfernt Datei"
        c8 = next(c for c in b["items"] if c["id"] == 8)
        assert c8["status"] == "namesake" and c8.get("namesake_reason")

        # -- 7) fertigen Batch nicht erneut anstoßen ------------------------
        code, out = BH.handle_action({"action": "upgrade_batch",
                                      "batch_id": bid})
        assert code == 400 and "nicht anstoßbar" in out["error"], (code, out)

        # -- 8) staged → partial → Wiederaufnahme OHNE Re-Download ----------
        U.cmd_scan(lib=Lib(lib1.items()
                           + [It(20, "GoneArt", "GoneTitle", "MP3",
                                 150, 200.0)]))
        st = U.load()
        bid2 = next(b["id"] for b in st["batches"] if b["status"] == "queued")

        mg2 = FakeMG(inc)  # search/FakeMG recordiert Queries selbst
        # Alle drei liefern Dateien; der asis-Fake lässt im ERSTEN Lauf
        # GoneArt liegen → partial; der zweite Lauf importiert nach
        # (keine neuen Downloads).

        def fake_asis2(unit_paths, progress=None):
            # asis_runs enthält bereits Sektion 6 — der ERSTE sec-8-Lauf
            # ist der zweite Eintrag insgesamt.
            first_run = len(asis_runs) < 2
            asis_runs.append(list(unit_paths))
            stx = state_mod.load()
            for up in unit_paths:
                u = state_mod.get_unit(stx, up)
                if not u or (first_run and "GoneArt" in (u.get("path") or "")):
                    continue
                for f in (u.get("files") or []):
                    if os.path.isfile(f):
                        os.remove(f)
                u["status"] = "asis"
            state_mod.save(stx)
            return ["✅ fake import"], False

        U._gate_file = lambda path, cand: ("ready", "")
        lines, failed = U.cmd_batch(
            bid2, progress=lambda l, i, t: None, lock_runner=lock_ok,
            mg_mod=mg2, scan_fn=fake_scan, asis_fn=fake_asis2,
            ingest_fn=fake_ingest, lib=Lib([]))
        st = U.load()
        b2 = next(x for x in st["batches"] if x["id"] == bid2)
        assert b2["results"].get("staged") == 1, b2["results"]
        assert b2["status"] == "partial", b2["status"]
        n_queries_first = len(mg2.queries)
        assert n_queries_first >= 3, mg2.queries

        lines, failed = U.cmd_batch(
            bid2, progress=lambda l, i, t: None, lock_runner=lock_ok,
            mg_mod=mg2, scan_fn=fake_scan, asis_fn=fake_asis2,
            ingest_fn=fake_ingest, lib=Lib([]))
        assert len(mg2.queries) == n_queries_first, "kein Re-Download!"
        st = U.load()
        b2 = next(x for x in st["batches"] if x["id"] == bid2)
        assert b2["status"] == "done", b2["status"]
        assert b2["results"]["staged"] == 0, b2["results"]
        assert b2["results"]["gone"] >= 1, "GoneArt-Datei weg, Lib leer"

        # -- 9) Lock verweigert → ingest-pending, nichts geladen ------------
        U.cmd_scan(lib=Lib([It(9, "XArt", "XTitle", "MP3", 128, 200.0)]))
        st = U.load()
        bid3 = next(b["id"] for b in st["batches"] if b["status"] == "queued")
        mg3 = FakeMG(inc)

        def lock_busy(fn, patience=0.0):
            return False

        lines, failed = U.cmd_batch(bid3, lock_runner=lock_busy, mg_mod=mg3)
        assert failed == 0, lines
        assert mg3.queries == [], "Download darf ohne Lock nicht starten"
        st = U.load()
        b3 = next(x for x in st["batches"] if x["id"] == bid3)
        assert b3["status"] == "ingest-pending", b3
        assert any("ingest-pending" in l for l in lines), lines

        # -- 10) no-source als dokumentiertes Ergebnis -----------------------
        U.cmd_scan(lib=Lib([It(5, "NoSrc Art", "NoSrc Title", "MP3",
                               96, 200.0)]))
        st = U.load()
        bid4 = next(b["id"] for b in st["batches"] if b["status"] == "queued")
        mg4 = FakeMG(inc)
        lines, failed = U.cmd_batch(bid4, lock_runner=lock_ok, mg_mod=mg4,
                                    scan_fn=fake_scan, asis_fn=fake_asis,
                                    ingest_fn=fake_ingest, lib=Lib([]))
        assert failed == 0, lines
        st = U.load()
        b4 = next(x for x in st["batches"] if x["id"] == bid4)
        assert b4["results"]["no_source"] == 1, b4["results"]
        assert b4["status"] == "done", b4["status"]

        # -- 11) MG nicht erreichbar: Batch bricht sauber --------------------
        U.cmd_scan(lib=Lib([It(11, "YArt", "YTitle", "MP3", 128, 200.0)]))
        st = U.load()
        bid5 = next(b["id"] for b in st["batches"] if b["status"] == "queued")

        class DownMG(FakeMG):
            def available(self):
                return False

        lines, failed = U.cmd_batch(bid5, lock_runner=lock_ok,
                                    mg_mod=DownMG(inc))
        assert failed == 1, lines
        assert any("fehlgeschlagen" in l for l in lines), lines
        st = U.load()
        b5 = next(x for x in st["batches"] if x["id"] == bid5)
        assert b5["status"] == "error", b5
        assert all(i.get("status") is None for i in b5["items"]), \
            "kein Track angefasst"

        # -- 12) Gate-Einzellogik (Dauer, Fingerprint, fehlende Alt-Datei) ---
        U._gate_file = real_gate  # Original zurücksichern
        orig_gate = U._gate_file
        U._audio_length = lambda p: 200.0 if "kurz" not in p else 190.0
        U._fp_similarity = lambda a, b: 0.9 if b else None
        U._stamp_tags = lambda p, c: None
        os.makedirs(os.path.join(inc, "g"), exist_ok=True)
        gp = os.path.join(inc, "g", "a.m4a")
        open(gp, "wb").close()
        oldp = os.path.join(inc, "g", "old.m4a")
        open(oldp, "wb").close()
        assert orig_gate(gp, {"length": 200.0, "path": oldp,
                              "artist": "A", "title": "T",
                              "album": "A"})[0] == "ready"
        assert orig_gate(gp.replace("a.m4a", "kurz.m4a"),
                         {"length": 200.0, "path": oldp, "artist": "A",
                          "title": "T", "album": "A"})[0] == "namesake"
        assert orig_gate(gp, {"length": 200.0, "path": oldp,
                              "artist": "A", "title": "T",
                              "album": "A"})[0] == "ready"  # fp 0.9
        U._fp_similarity = lambda a, b: (0.3 if (b and os.path.isfile(b))
                                         else None)
        assert orig_gate(gp, {"length": 200.0, "path": oldp,
                              "artist": "A", "title": "T",
                              "album": "A"})[0] == "namesake"
        # Alte Datei fehlt → fp aussetzbar, Dauer entscheidet
        assert orig_gate(gp, {"length": 200.0, "path": oldp + "weg",
                              "artist": "A", "title": "T",
                              "album": "A"})[0] == "ready"

        # -- 13) Token-Overlap (Fuzzy-Match-Regel) ---------------------------
        assert U._token_overlap("Wonderwall (live at Knebworth Park)",
                                "Wonderwall")
        assert not U._token_overlap("Wonderwall", "Champagne Supernova")

    print("smoke_upgrades: alle Assertionen grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
