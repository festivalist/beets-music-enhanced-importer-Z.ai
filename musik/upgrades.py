"""Track-Upgrades lossy → bestverfügbare Qualität (Story 3.3).

Scanner, Batch-Planer und Batch-Executor für Bibliotheks-Tracks unterhalb
der Qualitätsschwelle. Report-first: der Scan schreibt NIE die Bibliothek —
er listet Kandidaten, plant Batches und hält Nutzer-Entscheidungen
(Behalten) fest. Der Batch-Executor beschafft neu (dieselbe MG-Suche wie
Freitext-Bot-Anfragen, lossless-first, Cover-Guard) und überlässt die
Entscheidung dem bestehenden Import: der 2.3/2.8-Dupe-Vergleich behält
automatisch die bessere Kopie und archiviert den Verlierer nach _trash —
schlechtere Neukopien können die Bibliothek also nicht verschlechtern.

Zuständigkeits-Trennung (wie überall): beets bleibt die einzige
schreibende Instanz der Bibliothek; dieses Modul schreibt nur
state/upgrades.json und reports/upgrade-report.md. Entscheidungen (Batch
anstoßen, Track behalten) liegen beim Nutzer — im Import-Monitor.
"""

import json
import os
import tempfile
import time

from .paths import musik_config, reports_dir, state_dir

# Konfigurierbar über config.yaml `musik: upgrades:`; Defaults im Code,
# weil config.yaml gitignored und maschinenspezifisch ist (Pi).
DEFAULTS = {
    "threshold_kbps": 200,      # < Schwelle = Upgrade-Kandidat
    "batch_size": 109,          # Tracks je Nachladen-Batch (Nutzer-Vorgabe)
    "ingest_patience": 7200.0,  # Sek. Wartezeit auf den ingest.lock
}

# beets item.format-Werte, die als lossy gelten (FLAC/ALAC/APE/WAV nie).
LOSSY_FORMATS = {"MP3", "AAC", "MP4", "Opus", "Ogg", "OGG", "Vorbis",
                 "WMA", "MPC", "ASF"}

_FMT_TIER: dict | None = None


def _fmt_tier(fmt: str) -> int:
    """Format-String → Qualitätstier (aus quality.FORMAT_TIER abgeleitet),
    für den Reconcile-Vergleich neu vs. alt, ohne die (evtl. getrashte)
    alte Datei lesen zu müssen. Lazy: quality zieht mutagen."""
    global _FMT_TIER
    if _FMT_TIER is None:
        from .quality import FORMAT_TIER

        _FMT_TIER = {ext[1:].upper(): tier
                     for ext, tier in FORMAT_TIER.items()}
        _FMT_TIER.setdefault("MP4", 3)
        _FMT_TIER.setdefault("M4A", 3)
    return _FMT_TIER.get((fmt or "").upper(), 0)


def upgrades_config() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(musik_config().get("upgrades") or {})
    return cfg


# ---------------------------------------------------------------------------
# Scan + Kandidaten
# ---------------------------------------------------------------------------

def scan_candidates(lib=None, threshold_kbps: int | None = None):
    """Kandidaten = lossy Items unter der Schwelle, sortiert schlechteste
    zuerst. Items ohne Artist oder Title sind Junk (per MG-Suche nicht
    auffindbar) und werden ausgezählt, nicht gelistet. Reine Lese-Sicht."""
    if lib is None:
        from . import engine
        lib = engine.open_library()
    threshold_kbps = int(threshold_kbps
                         or upgrades_config()["threshold_kbps"])
    cands: list[dict] = []
    junk = 0
    for it in lib.items():
        fmt = it.format or ""
        kbps = int(getattr(it, "bitrate", 0) or 0) // 1000
        if fmt not in LOSSY_FORMATS or not 0 < kbps < threshold_kbps:
            continue
        artist = (it.artist or "").strip()
        title = (it.title or "").strip()
        if not artist or not title:
            junk += 1
            continue
        cands.append({
            "id": int(it.id),
            "artist": artist,
            "albumartist": (it.albumartist or "").strip(),
            "album": (it.album or "").strip(),
            "track": int(it.track or 0),
            "title": title,
            "format": fmt,
            "kbps": kbps,
            "length": round(float(getattr(it, "length", 0) or 0), 1),
            "path": os.fsdecode(it.path),
        })
    cands.sort(key=lambda c: (c["kbps"], c["artist"].lower(),
                              c["album"].lower(), c["track"]))
    return cands, {"threshold_kbps": threshold_kbps, "junk": junk}


def plan(state: dict) -> dict:
    """Batches frisch planen: Kandidaten ohne Behalten-Entscheid kommen in
    Stapel der konfigurierten Größe; bereits laufende/abgeschlossene
    Batches bleiben als Historie, offene (queued) verfallen zugunsten des
    neuen Plans."""
    size = int(state.get("batch_size") or upgrades_config()["batch_size"])
    kept_batches = [b for b in state.get("batches", [])
                    if b.get("status") != "queued"]
    batches = []
    free = [c for c in state.get("candidates", [])
            if c.get("decision") != "keep"]
    stamp = int(state.get("scanned_ts") or time.time())
    for i in range(0, len(free), size):
        chunk = free[i:i + size]
        # Fortlaufende Nummer über ALLE Batches (Historie inklusive): zwei
        # Scans in derselben Sekunde dürfen keine gleichlautenden IDs
        # erzeugen (Befund im Smoke: done + queued mit identischem bid).
        bid = f"upg-{stamp}-b{len(kept_batches) + len(batches) + 1:03d}"
        batches.append({
            "id": bid,
            "n": len(chunk),
            "status": "queued",
            "queued_ts": None,
            "started_ts": None,
            "finished_ts": None,
            "items": chunk,
            "results": {},
        })
    state["batches"] = kept_batches + batches
    for b in batches:
        for c in b["items"]:
            c["batch"] = b["id"]
    return state


def cmd_scan(lib=None, progress=None) -> tuple[list[str], int]:
    """Scan + Report + Batch-Plan; Behalten-Entscheidungen (je item id)
    überleben den Rescan. Liefert (Summary-Zeilen, failed 0/1)."""
    cfg = upgrades_config()
    try:
        cands, meta = scan_candidates(lib, cfg["threshold_kbps"])
    except Exception as e:
        return ([f"❌ Upgrade-Scan fehlgeschlagen: "
                 f"{type(e).__name__}: {str(e)[:200]}"], 1)
    old = load()
    kept_decisions = {c["id"]: c.get("decision")
                      for c in old.get("candidates", [])
                      if c.get("decision")}
    for c in cands:
        c["decision"] = kept_decisions.get(c["id"])
        c["batch"] = None
        c["status"] = None
    state = {
        "scanned_ts": time.time(),
        "threshold_kbps": meta["threshold_kbps"],
        "batch_size": int(cfg["batch_size"]),
        "junk_excluded": meta["junk"],
        "candidates": cands,
        "batches": old.get("batches", []),
    }
    plan(state)
    save(state)
    path = write_report(state)
    total = len(cands)
    kept = sum(1 for c in cands if c.get("decision") == "keep")
    n_batches = sum(1 for b in state["batches"] if b["status"] == "queued")
    lines = [
        f"🔍 Upgrade-Scan: {total} Kandidaten < {meta['threshold_kbps']} kbps"
        f" (lossy), {meta['junk']} Junk-Items ausgenommen"
        + (f", {kept} behalten" if kept else ""),
        f"📦 Plan: {n_batches} Batch/Batches à ≤ {state['batch_size']} "
        "— Entscheidungen im Import-Monitor",
        f"📄 Report: {path}",
    ]
    if progress:
        progress("\n".join(lines))
    return lines, 0


def write_report(state: dict) -> str:
    """reports/upgrade-report.md: Summary, Batch-Plan, Kandidaten
    (schlechteste zuerst) inkl. Behalten-Markierung."""
    path = os.path.join(reports_dir(), "upgrade-report.md")
    cands = state.get("candidates", [])
    by_fmt: dict = {}
    for c in cands:
        by_fmt[c["format"]] = by_fmt.get(c["format"], 0) + 1
    lines = [
        "# Upgrade report (Story 3.3)",
        "",
        f"Kandidaten: lossy < {state.get('threshold_kbps')} kbps — "
        f"{len(cands)} Stück"
        + (f", {state.get('junk_excluded')} Junk-Items ohne Artist/Title "
           "ausgenommen" if state.get("junk_excluded") else ""),
        "",
        "| format | tracks |",
        "|---|---|",
    ]
    for f in sorted(by_fmt):
        lines.append(f"| {f} | {by_fmt[f]} |")
    lines += ["", f"## Batch-Plan (à ≤ {state.get('batch_size')})", "",
              "| batch | tracks | status |", "|---|---|---|"]
    for b in state.get("batches", []):
        res = b.get("results") or {}
        status = b.get("status", "queued")
        if res:
            status += (f" — {res.get('replaced', 0)} ersetzt, "
                       f"{res.get('kept', 0)} behalten, "
                       f"{res.get('no_source', 0)} ohne Quelle"
                       + (f", {len(res.get('dup_risk', []))} prüfen"
                          if res.get("dup_risk") else ""))
        lines.append(f"| {b['id']} | {b['n']} | {status} |")
    lines += ["", "## Kandidaten (schlechteste zuerst)", "",
              "| kbps | format | artist | album | # | title | entscheidung |",
              "|---|---|---|---|---|---|---|"]
    for c in cands:
        lines.append(
            "| {kbps} | {format} | {artist} | {album} | {track} | {title} "
            "| {dec} |".format(
                kbps=c["kbps"], format=c["format"], artist=c["artist"],
                album=c["album"], track=c["track"], title=c["title"],
                dec="behalten" if c.get("decision") == "keep" else "-",
            ))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def cmd_decide(item_ids: list, decision) -> tuple[list[str], int]:
    """Nutzer-Entscheid je Kandidat: 'keep' (behalten, nicht nachladen)
    oder None (wieder freigeben). Schreibt nur upgrades.json."""
    st = load()
    by_id = {c["id"]: c for c in st.get("candidates", [])}
    done, missing = [], []
    for iid in item_ids:
        try:
            key = int(iid)
        except (TypeError, ValueError):
            missing.append(iid)
            continue
        c = by_id.get(key)
        if c is None:
            missing.append(iid)
            continue
        c["decision"] = "keep" if decision == "keep" else None
        done.append(f"{c['artist']} - {c['title']}")
    if done:
        save(st)
    label = "behalten" if decision == "keep" else "freigegeben"
    lines = [f"⬆️ {len(done)} Kandidat(en) {label}."]
    if missing:
        lines.append(f"⚠️ unbekannte/veraltete Item-Ids übersprungen: "
                     f"{missing[:5]}")
    return lines, 1 if missing and not done else 0


# ---------------------------------------------------------------------------
# Batch-Executor (nur Bot/Monitor) — beschafft, importiert, reconciled
# ---------------------------------------------------------------------------

def cmd_batch(batch_id: str, progress=None, lock_runner=None,
              mg_mod=None, ingest_fn=None, lib=None) -> tuple[list[str], int]:
    """Einen Batch abarbeiten: (1) je Kandidat MG-Suche + Download
    (best-3-Walk wie der Bot — kein Download ist ein dokumentiertes
    Ergebnis „ohne Quelle", kein Fehler), (2) EIN Ingest unter dem
    ingest.lock (der 2.3/2.8-Dupe-Vergleich ersetzt die bessere Kopie und
    trasht den Verlierer automatisch), (3) Reconcile je Kandidat gegen die
    frische Bibliothek. Ein Batch mit Status ingest-pending überspringt
    die Download-Phase (Dateien liegen schon im Staging bzw. sind
    importiert) und holt nur Ingest + Auswertung nach."""
    from . import ingest as ingest_mod

    st = load()
    batch = next((b for b in st.get("batches", [])
                  if b.get("id") == batch_id), None)
    if batch is None:
        return [f"❌ Upgrade-Batch {batch_id!r} unbekannt (Rescan? "
                "Neuen Batch-Plan im Monitor holen)"], 1
    if batch.get("status") not in ("queued", "error", "ingest-pending"):
        return [f"ℹ️ Batch {batch_id} läuft bereits oder ist fertig "
                f"({batch.get('status')})."], 0

    items = batch.get("items", [])
    batch["status"] = "running"
    batch["started_ts"] = batch.get("started_ts") or time.time()
    save(st)

    lines: list[str] = []
    if any(i.get("status") != "downloaded" for i in items):
        if mg_mod is None:
            from . import musicgrabber as mg_mod
        try:
            if not mg_mod.mg_config().get("enabled", True):
                raise mg_mod.MGUnavailable("MusicGrabber deaktiviert")
            if not mg_mod.available():
                raise mg_mod.MGUnavailable("nicht erreichbar")
            mg_mod.ensure_staging_layout()
        except Exception as e:
            batch["status"] = "error"
            batch["finished_ts"] = time.time()
            save(st)
            return [f"❌ Batch {batch_id} nicht gestartet — MusicGrabber "
                    f"({str(e)[:120]}). Kein Track berührt; Batch erneut "
                    "anstoßen, wenn MG wieder da ist."], 1
        to_dl = [i for i in items if i.get("status") != "downloaded"]
        # Behalten-Entscheidungen, die NACH der Batch-Planung gefallen sind,
        # gelten auch für den laufenden Batch — die Batch-Items sind
        # Snapshots, der aktuelle Entscheid-Stand liegt bei den Kandidaten.
        dec_now = {c.get("id"): c.get("decision")
                   for c in st.get("candidates", [])}
        for c in to_dl:
            if dec_now.get(c.get("id")) == "keep":
                c["status"] = "kept-user"
        to_dl = [i for i in to_dl if i.get("status") != "kept-user"]
        for idx, c in enumerate(to_dl, 1):
            note = _acquire_one(c, mg_mod)
            c["status"] = note["status"]
            c["source"] = note.get("source", "")
            c["quality"] = note.get("quality", "")
            if progress:
                progress(f"⬆️ {idx}/{len(to_dl)}: {c['artist']} - "
                         f"{c['title']} · {note['status']}"
                         + (f" [{c['source']} {c['quality']}]"
                            if c.get("source") else ""),
                         idx, len(to_dl))
        dl_ok = sum(1 for i in items if i.get("status") == "downloaded")
        no_src = sum(1 for i in items if i.get("status") == "no-source")
        lines.append(f"⬇️ nachgeladen: {dl_ok}/{len(items)}"
                     + (f" ({no_src} ohne brauchbare Quelle)"
                        if no_src else ""))
        save(st)

    # Import: EIN Lauf für den ganzen Batch, unter demselben Lock wie der
    # Timer. Lock dauerhaft belegt (patience) → ingest-pending; Wiederaufnahme
    # ohne Re-Download. Ganz ohne Download (alles kept-user/no-source)
    # gibt es nichts zu importieren — Ingest + Lib-Hydration entfallen.
    if not any(i.get("status") == "downloaded" for i in items):
        results = _reconcile(None, items)
        batch["results"] = results
        batch["status"] = "done"
        batch["finished_ts"] = time.time()
        save(st)
        lines.append(_results_line(batch_id, len(items), results))
        return lines, 0
    ingest_callable = ingest_fn or ingest_mod.cmd_ingest
    runner = lock_runner
    if runner is None:
        from .bot import _run_exclusive as runner
    try:
        locked = runner(ingest_callable,
                        patience=float(upgrades_config()["ingest_patience"]))
    except Exception as e:
        batch["status"] = "error"
        batch["finished_ts"] = time.time()
        save(st)
        return [f"❌ Batch {batch_id}: Ingest fehlgeschlagen: "
                f"{type(e).__name__}: {str(e)[:200]}"], 1
    if not locked:
        batch["status"] = "ingest-pending"
        save(st)
        lines.append("⏳ ingest.lock dauerhaft belegt — Batch als "
                     "ingest-pending gemerkt. Erneut anstoßen holt nur "
                     "Ingest + Auswertung nach (kein Re-Download).")
        return lines, 0

    if lib is None:
        from . import engine
        lib = engine.open_library()
    results = _reconcile(lib, items)
    batch["results"] = results
    batch["status"] = "done"
    batch["finished_ts"] = time.time()
    save(st)
    lines.append(_results_line(batch_id, len(items), results))
    return lines, 0


def _acquire_one(cand: dict, mg_mod) -> dict:
    """Ein Track über MG beschaffen: Suche → best-3-Walk (MGs Qualitäts-
    gate lehnt Rank 1 manchmal ab, die nächste Quelle liefert oft).
    Kein brauchbarer Download = Status no-source (dokumentiertes
    Ergebnis), kein Fehler."""
    query = f"{cand['artist']} - {cand['title']}"
    try:
        token, results = mg_mod.search(query, limit=10)
        ranked = mg_mod.ranked_results(query, results)
    except Exception:
        return {"status": "no-source"}
    for pick in ranked[:3]:
        try:
            job_id = mg_mod.download(pick, token)
            mg_mod.wait_for_job(job_id)
        except Exception:
            continue
        return {"status": "downloaded",
                "source": pick.get("source", ""),
                "quality": pick.get("quality") or ""}
    return {"status": "no-source"}


def _reconcile(lib, items: list[dict]) -> dict:
    """Je nachgeladenem Kandidat die Bibliothek prüfen: replaced (bessere
    Kopie liegt jetzt in der Lib), kept (Quelle nicht besser — der Dupe-
    Check hat die schlechtere Neukopie automatisch archiviert), dup_risk
    (mehr als ein Match — händisch prüfen), gone (kein Match mehr).
    lib=None (Fast-Pfad: nichts nachgeladen) überspringt die Hydration."""
    from .scan import norm_name

    hydrated = []
    if lib is not None:
        for it in lib.items():
            hydrated.append((
                (norm_name(getattr(it, "artist", "") or ""),
                 norm_name(getattr(it, "title", "") or "")),
                float(getattr(it, "length", 0) or 0),
                it,
            ))
    counts = {"replaced": 0, "kept": 0, "no_source": 0, "gone": 0}
    dup_risk: list[str] = []
    for c in items:
        status = c.get("status")
        if status == "no-source":
            counts["no_source"] += 1
            continue
        if status != "downloaded":
            counts["kept"] += 1
            continue
        pair = (norm_name(c["artist"]), norm_name(c["title"]))
        length = float(c.get("length") or 0)
        exact, fuzzy = [], []
        for hp, hlen, it in hydrated:
            if abs(hlen - length) > 15:
                continue
            if hp == pair:
                exact.append(it)
            elif (_token_overlap(c["title"], it.title)
                  and _token_overlap(c["artist"], it.artist)):
                fuzzy.append(it)
        matches = exact or fuzzy
        if not matches:
            counts["gone"] += 1
            continue
        if len(matches) > 1:
            dup_risk.append(f"{c['artist']} - {c['title']} "
                            f"({len(matches)} Kopien)")
            continue
        if _quality_tuple(matches[0]) > (_fmt_tier(c["format"]), c["kbps"]):
            counts["replaced"] += 1
        else:
            counts["kept"] += 1
    counts["dup_risk"] = dup_risk
    return counts


def _quality_tuple(item) -> tuple:
    fmt = (getattr(item, "format", "") or "").upper()
    kbps = int(getattr(item, "bitrate", 0) or 0) // 1000
    return (_fmt_tier(fmt), kbps)


def _token_overlap(a: str, b: str) -> bool:
    """Jeder Token des kürzeren Strings steckt im anderen (Reihenfolge-
    und Zusatz-Robustheit, z. B. feat-Credits nach dem MB-Retitle)."""
    from .scan import norm_name

    ta = set(norm_name(a or "").split())
    tb = set(norm_name(b or "").split())
    if not ta or not tb:
        return False
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return small <= big


def _results_line(batch_id: str, total: int, res: dict) -> str:
    line = (f"✅ Batch {batch_id}: {res.get('replaced', 0)} ersetzt "
            f"/ {total} Tracks · {res.get('kept', 0)} behalten (Quelle "
            f"nicht besser) · {res.get('no_source', 0)} ohne Quelle"
            + (f" · {res['gone']} nicht mehr auffindbar"
               if res.get("gone") else ""))
    if res.get("dup_risk"):
        line += (f"\n⚠️ prüfen ({len(res['dup_risk'])} Mehrfach-Kopien):\n"
                 + "\n".join(f"- {d}" for d in res["dup_risk"][:5]))
    return line


# ---------------------------------------------------------------------------
# State (state/upgrades.json) — atomar; schreibend ist nur der Bot-Worker
# (Jobs laufen seriell), HTTP-Handler liest nur.
# ---------------------------------------------------------------------------

def _file() -> str:
    return os.path.join(state_dir(), "upgrades.json")


def load() -> dict:
    try:
        with open(_file(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save(state: dict) -> None:
    d = state_dir()
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
        os.replace(tmp, _file())
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def summary() -> dict:
    """Leichte Sicht für den 5-s-Snapshot (keine Kandidaten-Liste)."""
    st = load()
    cands = st.get("candidates", [])
    return {
        "scanned_ts": st.get("scanned_ts"),
        "threshold_kbps": st.get("threshold_kbps"),
        "batch_size": st.get("batch_size"),
        "total": len(cands),
        "kept": sum(1 for c in cands if c.get("decision") == "keep"),
        "batches": [
            {"id": b.get("id"), "n": b.get("n"), "status": b.get("status"),
             "results": b.get("results") or {}}
            for b in st.get("batches", [])
        ],
    }


def detail() -> dict:
    """Kompletter Zustand für GET /api/upgrades (on-demand im Tab)."""
    return load()


def cmd_cli() -> int:
    """`musik upgrades`: Scan + Report + Batch-Plan, Ausgabe auf stdout."""
    lines, failed = cmd_scan()
    for ln in lines:
        print(ln)
    return 1 if failed else 0
