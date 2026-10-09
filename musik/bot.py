"""Telegram bot service (`musik bot`).

Send the bot a Spotify/YouTube link (or 'artist - title' search text);
it downloads via spotDL/SomeDL, runs the full musik import chain and
reports back — no local network access needed (long polling).

Setup:
1. Create a bot with @BotFather, put its token into telegram_token.json
   next to config.yaml: {"token": "123456:ABC-DEF..."}
2. Allow your chat: send the bot any message once, it replies with your
   chat id; add that id to config.yaml under `musik: bot_allowlist: [123]`.
3. `musik bot` and leave it running (systemd on the Pi).

This bot is independent of the ZCode desktop Telegram relay.
"""

import asyncio
import json
import os
import threading
import time
import traceback

from collections import Counter

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import asis as asis_mod
from . import fetch
from . import jobs as jobs_mod
from . import plex as plex_mod
from . import playlists as playlists_mod
from . import state as state_mod
from .paths import PROJECT_DIR, bootstrap, musik_config
from .scan import artist_values

MAX_MESSAGE_LEN = 400


def _token_file() -> str:
    return musik_config().get("telegram_tokenfile") or os.path.join(
        PROJECT_DIR, "telegram_token.json"
    )


def _load_token() -> str | None:
    try:
        with open(_token_file(), encoding="utf-8") as fh:
            token = (json.load(fh) or {}).get("token", "").strip()
        return token or None
    except (OSError, ValueError):
        return None


def _allowlist() -> list[int]:
    return [int(x) for x in (musik_config().get("bot_allowlist") or [])]


def _chat_id(update: Update) -> int | None:
    return update.effective_chat.id if update.effective_chat else None


def _authorized(update: Update) -> bool:
    cid = _chat_id(update)
    return cid is not None and cid in _allowlist()


HELP_TEXT = (
    "Schick mir einfach:\n"
    "• einen Spotify-Link (Album, Playlist, Track, Artist)\n"
    "• einen YouTube/YT-Music-Link\n"
    "• oder Suchtext: „artist - title“ (läuft zuerst über MusicGrabber — "
    "mehrere Quellen inkl. Lossless, Qualitäts-Auswahl; Fallback: YouTube)\n\n"
    "Ich lade die Tracks herunter, tagge und importiere sie in die "
    "Musikbibliothek und melde mich, wenn sie fertig sind.\n\n"
    "Nach einer Track-Suche biete ich per Knopfdruck das passende Album / "
    "die EP an (bis zu 5 Kandidaten, Original zuerst, die neueste "
    "Veröffentlichung immer dabei, bevorzugt Lossless) — ein Tipp genügt.\n\n"
    "/asis — liegengeschlafene Einheiten (Review etc.) auflisten und "
    "per Knopfdruck auf eigene Tags importieren\n"
    "/status — Warteschlange und letzte Ergebnisse"
)


# --------------------------------------------------------------------------
# worker (runs in a thread; one job at a time)
# --------------------------------------------------------------------------

def _is_free_text(query: str) -> bool:
    """True for plain search text (no Spotify/YouTube link) — those go to
    MusicGrabber first; links keep the spotDL/SomeDL chain."""
    try:
        pairs = fetch.classify(query)
    except Exception:
        return False
    return bool(pairs) and all(kind == "search" for kind, _value in pairs)


def _try_musicgrabber(job: dict, query: str, send) -> bool:
    """Route a free-text search through MusicGrabber (multi-source, quality
    tiers, MusicBrainz duration check) and import the result immediately.
    Returns False (with a notice) when MG cannot deliver — the caller then
    runs the usual spotDL/SomeDL fallback."""
    from . import musicgrabber as mg

    if not mg.mg_config().get("enabled", True):
        return False
    try:
        if not mg.available():
            send("ℹ️ MusicGrabber nicht erreichbar — Fallback über YouTube-Kette")
            return False
        # MG writes into Singles//Albums/ without mkdir — self-heal the
        # staging skeleton before queueing anything (ENOENT incident)
        mg.ensure_staging_layout()
        send(f"🔍 MusicGrabber-Suche: {query[:120]}")
        token, results = mg.search(query, limit=10)
        pick = mg.pick_result(query, results)
        if pick is None:
            send("ℹ️ MusicGrabber: keine Ergebnisse — Fallback über YouTube-Kette")
            return False
        quality = f" | {pick['quality']}" if pick["quality"] else ""
        send(f"⬇️ via MusicGrabber [{pick['source']}{quality}]:\n"
             f"{pick['artist'][:60]} - {pick['title'][:80]}")
        job_id = mg.download(pick, token)
        mg.wait_for_job(job_id)
        # file is in the MG staging area -> import now, no 15-min-timer wait
        # (the ingest timer's flock skips while this run holds the same
        # library; ingest itself refreshes Plex at the end)
        from . import ingest as ingest_mod

        send("📦 geladen — Import & Tagging laufen…")
        ingest_mod.cmd_ingest()
        summary = (f"✅ via MusicGrabber [{pick['source']}{quality}] "
                   f"importiert: {pick['artist'][:50]} - {pick['title'][:70]}")
        send(summary)
        jobs_mod.update_job(job["id"], status="done", finished=time.time(),
                            summary=summary)
        print(f"bot: job {job['id']} done (musicgrabber)")
        # "whole album instead?" buttons — after the summary, so the track
        # result reads first; silent best-effort (never breaks the job)
        _maybe_album_offer(job, query, pick, send)
        return True
    except mg.MGJobFailed as e:
        send(f"⚠️ MusicGrabber fehlgeschlagen ({str(e)[:150]}) — "
             "Fallback über YouTube-Kette")
        return False
    except mg.MGUnavailable as e:
        send(f"⚠️ MusicGrabber nicht erreichbar ({str(e)[:100]}) — "
             "Fallback über YouTube-Kette")
        return False


def _execute_job(job: dict, send) -> None:
    """Run one job end to end; `send` delivers progress messages."""
    jobs_mod.update_job(job["id"], status="running", started=time.time())
    if job.get("kind") == "asis":
        _execute_asis(job, send)
        return
    if job.get("kind") == "album":
        _execute_album(job, send)
        return
    query = job["text"].strip()
    print(f"bot: job {job['id']} running: {query[:120]}")
    if _is_free_text(query) and _try_musicgrabber(job, query, send):
        return
    send(f"⬇️ Download läuft:\n{query[:200]}")
    try:
        fetch_jobs = fetch.run_fetch([query])
        if not fetch_jobs:
            msg = "Keine unterstützte Quelle erkannt — Spotify- oder YouTube-Link schicken."
            send(msg)
            jobs_mod.update_job(job["id"], status="error", finished=time.time(),
                                summary=msg)
            return
        summaries = []
        for fj in fetch_jobs:
            if fj.files:
                send(f"📦 {len(fj.files)} Track(s) geladen — Import & Tagging laufen…")
                fetch._import_job(fj)
                ok, note = plex_mod.refresh_library()
                if ok:
                    send(f"🎧 {note} — neues Album ist gleich in Plexamp sichtbar")
                elif note:  # configured but failed
                    send(f"⚠️ {note}")
                # playlist upload waits for the scan it just triggered
                for msg in playlists_mod.upload(fj.playlists):
                    send(msg)
            summaries.append(fetch.summarize_job(fj))
            send(summaries[-1])
        jobs_mod.update_job(job["id"], status="done", finished=time.time(),
                            summary="\n—\n".join(summaries)[:1500])
        print(f"bot: job {job['id']} done")
        # free text fell back to the spotDL/SomeDL chain (MG could not
        # deliver) — the album offer belongs to the REQUEST, not to the
        # engine, so it fires here too (live case 2026-10-09: MG staging
        # ENOENT → fallback import → user wondered about the missing offer)
        if _is_free_text(query):
            _maybe_album_offer(job, query, {}, send)
    except Exception as e:
        traceback.print_exc()
        msg = f"❌ Job fehlgeschlagen: {type(e).__name__}: {str(e)[:300]}"
        send(msg)
        jobs_mod.update_job(job["id"], status="error", finished=time.time(),
                            summary=msg)
        print(f"bot: job {job['id']} error")


def _execute_asis(job: dict, send) -> None:
    """Import the job's units as-is (own tags); report per-unit outcomes."""
    paths = job.get("unit_paths") or []
    lines = []
    for p in paths:
        label = os.path.basename(p) or p
        send(f"📦 as-is-Import läuft:\n{label}")
        try:
            asis_mod.cmd_asis(only=p, include_pending=True)
        except Exception as e:
            traceback.print_exc()
            lines.append(f"❌ {label}: {type(e).__name__}: {str(e)[:200]}")
            continue
        fresh = state_mod.get_unit(state_mod.load(), p)
        status = (fresh or {}).get("status")
        if status == "asis":
            lines.append(f"✅ {os.path.basename(p) or p} — importiert")
        else:
            why = ((fresh or {}).get("reason") or "")[:120]
            lines.append(f"⚠️ {os.path.basename(p) or p} — Status jetzt "
                         f"„{status}“ {('('+why+')') if why else ''}")
    ok, note = plex_mod.refresh_library()
    if ok:
        lines.append(f"🎧 {note}")
    elif note:
        lines.append(f"⚠️ {note}")
    # tracks that just arrived fill their playlist entries -> re-upload
    for msg in playlists_mod.upload(playlists_mod.rebuild(paths)):
        lines.append(msg)
    summary = "\n".join(lines)[:1500]
    failed = any(l.startswith("❌") for l in lines)
    jobs_mod.update_job(job["id"],
                        status="error" if failed else "done",
                        finished=time.time(), summary=summary)
    send(summary or "fertig")


def _asis_candidates() -> list[dict]:
    """Units waiting in review/unmatched/network/pending whose files can
    import on their own tags, annotated with a human label."""
    out = []
    st = state_mod.load()
    for u in state_mod.units(st).values():
        if u.get("status") not in ("review", "unmatched", "network", "pending"):
            continue
        present = [f for f in (u.get("files") or []) if os.path.isfile(f)]
        if not present:
            continue
        u = dict(u)
        u["files"] = present
        u["n_files"] = len(present)
        ok, _why = asis_mod.tags_complete(u)
        if not ok:
            continue
        tags = [t for t in artist_values(present) if t]
        if tags:
            artist = Counter(tags).most_common(1)[0][0].title()
        else:
            artist = (u.get("guessed") or {}).get("artist") \
                or os.path.basename(u.get("import_path") or "?")
        u["label"] = f"{artist} · {u['n_files']} Tracks ({u['status']})"
        out.append(u)
    out.sort(key=lambda u: u["path"])
    return out[:10]


# --------------------------------------------------------------------------
# album offer (free-text track request → "whole album instead?" buttons)
# --------------------------------------------------------------------------

# pending offers: callback key -> payload; wiped on restart (stale taps get
# an alert, same contract as asis_map). Guarded because the worker thread
# writes and the async callback handler reads.
_ALBUM_OFFERS: dict[str, dict] = {}
_ALBUM_LOCK = threading.Lock()
_ALBUM_SEQ = [0]
_ALBUM_OFFER_MAX = 30  # forget ancient offers, not today's


def _open_library():
    from .engine import setup_beets

    setup_beets()
    from beets import config as beets_config
    from beets.library import Library

    return Library(beets_config["library"].as_filename(),
                   beets_config["directory"].as_filename())


def _find_singleton(lib, artist: str, title: str) -> int | None:
    """The item this track request just created (artist/title match,
    singleton = no album row, newest added first). Its id rides along in
    the album offer so the album job can remove the now-redundant copy."""
    try:
        items = [i for i in lib.items(f"artist:{artist} title:{title}")
                 if not i.album_id]
        if not items:
            return None
        return max(items, key=lambda i: i.added or 0).id
    except Exception:
        traceback.print_exc()
        return None


def _remove_singleton(item_id) -> str:
    """Delete the track-request singleton (row + file) once the album
    import has verifiably brought the same song. Returns a label or ''."""
    if not item_id:
        return ""
    try:
        lib = _open_library()
        item = lib.get_item(item_id)
        if item is None:
            return ""
        label = f"{item.artist} - {item.title}"
        item.remove(delete=True)
        return label
    except Exception:
        traceback.print_exc()
        return ""


def _maybe_album_offer(job: dict, query: str, pick: dict, send) -> None:
    """After a successful free-text track import: offer the containing
    albums/EPs as buttons (MusicBrainz candidates; up to 5, canonical
    first — score, reissue weight, year ascending — with the NEWEST always
    included; user rules 2026-10-09). The offer is pure
    best-effort: any problem means no offer, never a failed track job."""
    from . import musicgrabber as mg
    from .releases import track_album_candidates

    if not mg.mg_config().get("album_offer", True):
        return
    try:
        if " - " in query:
            artist, title = query.split(" - ", 1)
        else:
            artist = pick.get("artist") or ""
            title = pick.get("title") or ""
        artist, title = artist.strip(), title.strip()
        if not artist or not title:
            return
        lib = _open_library()
        cands = track_album_candidates(artist, title, library=lib)
        if not cands:
            return
        singleton_id = _find_singleton(lib, artist, title)
    except Exception:
        traceback.print_exc()
        return

    with _ALBUM_LOCK:
        _ALBUM_SEQ[0] += 1
        seq = _ALBUM_SEQ[0]
        while len(_ALBUM_OFFERS) >= _ALBUM_OFFER_MAX:
            _ALBUM_OFFERS.pop(next(iter(_ALBUM_OFFERS)))
    rows = []
    for i, c in enumerate(cands):
        icon = "💽" if c.get("type") == "ep" else "💿"
        mark = " ✓" if c.get("in_library") else ""
        year = f" ({c['year']})" if c.get("year") else ""
        label = f"{icon} {c['title'][:40]}{year}{mark}"
        key = f"{seq}:{i}"
        with _ALBUM_LOCK:
            _ALBUM_OFFERS[key] = {
                "rg_mbid": c["rg_mbid"], "artist": c.get("artist") or artist,
                "album_title": c["title"], "year": c.get("year") or "",
                "type": c.get("type") or "album",
                "track_artist": artist, "track_title": title,
                "singleton_id": singleton_id, "chat_id": job["chat_id"],
            }
        rows.append([InlineKeyboardButton(label, callback_data=f"album:{key}")])
    with _ALBUM_LOCK:
        _ALBUM_OFFERS[f"{seq}:no"] = {"dismiss": True, "chat_id": job["chat_id"]}
    rows.append([InlineKeyboardButton("✖ Nur den Track behalten",
                                      callback_data=f"album:{seq}:no")])
    send(f"„{title[:60]}“ liegt auf — das Ganze laden?\n"
         "(MusicGrabber, mehrere Quellen, bevorzugt Lossless; "
         "✓ = Album bereits vorhanden, wird nur ergänzt)",
         markup=InlineKeyboardMarkup(rows))


def _execute_album(job: dict, send) -> None:
    """Whole-album download via MusicGrabber: resolve the release group to
    a concrete release, queue the per-track bulk import, wait, ingest, then
    remove the track-request singleton the album supersedes. Partial
    results (some tracks failed at the sources) are reported, not fatal."""
    from . import musicgrabber as mg

    a = job.get("album") or {}
    rg_mbid = a.get("rg_mbid") or ""
    label = f"{a.get('artist', '?')} - {a.get('album_title', '?')}"
    if not rg_mbid:
        msg = f"❌ Album-Job ohne Release-Group (Bot-Neustart?) — {label}"
        send(msg)
        jobs_mod.update_job(job["id"], status="error", finished=time.time(),
                            summary=msg)
        return
    try:
        mg.ensure_staging_layout()  # ENOENT guard: Albums/ must exist
        send(f"🔍 löse das Release auf: {label[:120]}")
        summary = mg.resolve_release_group(rg_mbid)
        artist = summary.get("artist") or a.get("artist") or "?"
        album_title = summary.get("album_title") or a.get("album_title") or "?"
        d = mg.download_album(artist, album_title, summary["release_mbid"])
        total = d.get("track_count") or summary.get("track_count") or 0
        jobs_mod.update_job(job["id"],
                            mg_import={"import_id": d["import_id"],
                                       "total": total})
        send(f"⬇️ Album-Download läuft: {album_title[:80]} — "
             f"{total} Track(s) via MusicGrabber")

        # one progress line per minute, not per 10-second poll
        last_note = [0.0]

        def _progress(st: dict) -> None:
            now = time.monotonic()
            if now - last_note[0] < 60:
                return
            last_note[0] = now
            done, tot = st.get("completed", 0), st.get("total_tracks", total)
            failed = st.get("failed", 0)
            extra = f", {failed} fehlgeschlagen" if failed else ""
            send(f"⏱ {done}/{tot} Track(s) geladen{extra}")

        result = mg.wait_for_import(d["import_id"], progress=_progress)

        from . import ingest as ingest_mod

        send("📦 geladen — Import & Tagging laufen …")
        ingest_mod.cmd_ingest()

        removed = _remove_singleton(a.get("singleton_id"))
        ok, note = plex_mod.refresh_library()
        lines = [f"✅ {album_title[:80]}: {result.get('completed', 0)}/"
                 f"{result.get('total_tracks', total)} Track(s) importiert"]
        if removed:
            lines.append(f"🧹 Single-Version entfernt ({removed})")
        failed_tracks = [t for t in result.get("tracks") or []
                         if (t.get("status") or "").lower() == "failed"]
        if failed_tracks:
            names = "; ".join(t.get("song") or t.get("title") or "?"
                              for t in failed_tracks[:5])[:280]
            lines.append(f"⚠️ {len(failed_tracks)} Track(s) nicht lieferbar: "
                         f"{names}")
        if result.get("dupe_skipped"):
            lines.append(f"♻️ {result['dupe_skipped']} bereits vorhanden "
                         "(übersprungen)")
        if ok:
            lines.append(f"🎧 {note}")
        elif note:
            lines.append(f"⚠️ {note}")
        summary_text = "\n".join(lines)[:1500]
        send(summary_text)
        jobs_mod.update_job(job["id"], status="done", finished=time.time(),
                            summary=summary_text)
        print(f"bot: job {job['id']} done (album)")
    except mg.MGUnavailable as e:
        _album_failed(job, send, label, f"MusicGrabber nicht erreichbar ({str(e)[:150]})")
    except mg.MGJobFailed as e:
        _album_failed(job, send, label, str(e)[:200])
    except Exception as e:  # never leave the job stuck in "running"
        traceback.print_exc()
        _album_failed(job, send, label,
                      f"{type(e).__name__}: {str(e)[:200]}")


def _album_failed(job: dict, send, label: str, reason: str) -> None:
    """No silent engine downgrade: albums stay lossless-first on MG; the
    Spotify-album link remains the lossy alternative the user can choose."""
    msg = (f"❌ Album-Download fehlgeschlagen ({label[:80]}): {reason}\n"
           "Alternativ: Spotify-Album-Link schicken (läuft über die "
           "spotDL-Kette).")
    send(msg)
    jobs_mod.update_job(job["id"], status="error", finished=time.time(),
                        summary=msg)
    print(f"bot: job {job['id']} error (album)")


def _run_job(job: dict, app, loop) -> None:
    chat_id = job["chat_id"]

    def send(text: str, markup=None) -> None:
        try:
            fut = asyncio.run_coroutine_threadsafe(
                app.bot.send_message(chat_id=chat_id, text=text[:4000],
                                     reply_markup=markup), loop
            )
            fut.result(timeout=60)
        except Exception as e:  # never let a telegram hiccup kill a job
            print(f"bot: send failed: {e}")

    _execute_job(job, send)


async def _worker(app) -> None:
    queue: asyncio.Queue = app.bot_data["queue"]
    loop = asyncio.get_running_loop()
    while True:
        job = await queue.get()
        try:
            await asyncio.to_thread(_run_job, job, app, loop)
        except Exception:
            traceback.print_exc()
        finally:
            queue.task_done()


async def _post_init(app) -> None:
    app.bot_data["queue"] = asyncio.Queue()
    app.create_task(_worker(app))
    me = await app.bot.get_me()
    print(f"bot: listening as @{me.username} (long polling, Ctrl+C to stop)")


# --------------------------------------------------------------------------
# handlers
# --------------------------------------------------------------------------

async def _deny(update: Update) -> None:
    cid = _chat_id(update)
    # surfaced in the service log so the operator can lift the id into
    # bot_allowlist without asking the user to copy it around
    print(f"bot: unauthorized message from chat {cid} "
          f"(@{(update.effective_user or None) and update.effective_user.username})",
          flush=True)
    await update.effective_message.reply_text(
        f"🚫 Nicht autorisiert.\n"
        f"Deine Chat-ID ist {cid} — trage sie in config.yaml ein unter\n"
        f"musik: bot_allowlist: [{cid}]\nund starte den Bot neu."
    )


async def _cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _deny(update)
        return
    await update.effective_message.reply_text(
        f"Moin! 👋\n\n{HELP_TEXT}"
    )


async def _cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _deny(update)
        return
    await update.effective_message.reply_text(HELP_TEXT)


def _running_progress() -> str:
    """Live progress for the running fetch job: files landed so far in the
    staging dir plus the downloader's own `N/M` count from the newest log
    (SomeDL prints `7/12`, spotDL similar). Best-effort — newest dir/log
    is the active job because only one job runs at a time."""
    import glob
    import re as _re

    from .paths import incoming_dir, reports_dir
    from .scan import collect_audio_tree

    out = []
    try:
        dirs = sorted(
            (d for d in glob.glob(os.path.join(incoming_dir(), "fetch-*"))
             if os.path.isdir(d)),
            key=os.path.getmtime,
        )
        if dirs:
            out.append(f"   📥 {len(collect_audio_tree(dirs[-1]))} Datei(en) geladen")
    except OSError:
        pass
    try:
        logs = sorted(
            glob.glob(os.path.join(reports_dir(), "fetch", "*.log")),
            key=os.path.getmtime,
        )
        if logs:
            with open(logs[-1], "rb") as fh:
                fh.seek(max(0, os.path.getsize(logs[-1]) - 4096))
                tail = fh.read().decode("utf-8", "replace")
            m = _re.findall(r"(\d+)\s*/\s*(\d+)", tail)
            if m:
                out.append(f"   ⏱ Fortschritt: {m[-1][0]}/{m[-1][1]}")
    except OSError:
        pass
    return "\n".join(out)


def _mg_import_progress(mg_import: dict) -> str:
    """Live 'N/M Tracks' line for a running album job (MusicGrabber's own
    per-track counters — the fetch-log tail doesn't exist for MG jobs)."""
    from . import musicgrabber as mg

    try:
        st = mg.import_status(mg_import.get("import_id"))
        done = st.get("completed", 0)
        total = st.get("total_tracks", mg_import.get("total") or "?")
        extra = f", {st['failed']} fehlgeschlagen" if st.get("failed") else ""
        return f"   ⏱ {done}/{total} Track(s) geladen{extra} (MusicGrabber)"
    except Exception:
        return ""


async def _cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _deny(update)
        return
    stats = jobs_mod.queue_stats()
    lines = []
    if stats["running_job"]:
        r = stats["running_job"]
        lines.append(f"🔄 läuft: {r['text'][:80]}")
        if r.get("mg_import"):
            try:
                info = await asyncio.to_thread(_mg_import_progress,
                                               r["mg_import"])
                if info:
                    lines.append(info)
            except Exception:
                pass
        else:
            prog = _running_progress()
            if prog:
                lines.append(prog)
    else:
        lines.append("💤 gerade läuft nichts")
    lines.append(f"⏳ in Warteschlange: {stats['queued']}")
    for j in stats["recent"]:
        icon = "✅" if j["status"] == "done" else "❌"
        summary = j.get("summary") or ""
        head = summary.splitlines()[0][:80] if summary else j["text"][:60]
        lines.append(f"{icon} {head}")
        # the playlist result (🎵 … N/N zugeordnet) lives on a later line —
        # surface it so /status answers "10/30 importiert?" directly
        for extra in summary.splitlines():
            if "🎵" in extra or "Plex-Playlist" in extra:
                lines.append(f"     {extra.strip()[:90]}")
                break
    await update.effective_message.reply_text("\n".join(lines))


async def _cmd_asis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _deny(update)
        return
    cands = await asyncio.to_thread(_asis_candidates)
    if not cands:
        await update.effective_message.reply_text(
            "Nichts angetan: keine Einheiten mit vollständigen Tags in "
            "review/unmatched/pending. (/status zeigt, was zuletzt lief)")
        return
    mapping = context.bot_data.setdefault("asis_map", {})
    mapping.clear()
    rows = []
    for i, u in enumerate(cands, 1):
        mapping[str(i)] = u["path"]
        rows.append([InlineKeyboardButton(
            f"{i}. {u['label']}", callback_data=f"asis:{i}")])
    if len(cands) > 1:
        rows.append([InlineKeyboardButton(
            "✅ ALLE importieren", callback_data="asis:all")])
    await update.effective_message.reply_text(
        "Diese Einheiten können auf eigene Tags importiert werden "
        "(as-is) — antippen:\n"
        "Playlists landen dabei Track-für-Track in ihren echten Alben; "
        "eine zugehörige Plex-Playlist wird automatisch ergänzt.",
        reply_markup=InlineKeyboardMarkup(rows))


async def _on_asis_callback(update: Update,
                            context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not _authorized(update):
        await query.answer("🚫 nicht autorisiert", show_alert=True)
        return
    sel = (query.data or "").split(":", 1)[-1]
    mapping = context.bot_data.get("asis_map") or {}
    if sel == "all":
        paths = list(mapping.values())
    else:
        one = mapping.get(sel)
        paths = [one] if one else []
    if not paths:
        await query.answer("Veraltete Liste (Bot wurde neu gestartet) — "
                           "schick /asis erneut", show_alert=True)
        return
    await query.answer()
    job = jobs_mod.add_job(f"/asis {len(paths)} unit(s)", _chat_id(update))
    job["kind"] = "asis"
    job["unit_paths"] = paths
    await context.bot_data["queue"].put(job)
    await update.effective_message.reply_text(
        f"✅ as-is-Import angenommen ({len(paths)} Einheit(en)) — "
        "du bekommst das Ergebnis hier.")


async def _on_album_callback(update: Update,
                             context: ContextTypes.DEFAULT_TYPE) -> None:
    """Album-offer button tap: dismiss, or enqueue the album download as a
    regular queue job (serial worker stays fair; the tap pops the offer so
    double-taps cannot double-queue)."""
    query = update.callback_query
    if not _authorized(update):
        await query.answer("🚫 nicht autorisiert", show_alert=True)
        return
    key = ":".join((query.data or "").split(":")[1:3])
    with _ALBUM_LOCK:
        offer = _ALBUM_OFFERS.pop(key, None)
    if offer is None:
        await query.answer("Angebot ist veraltet (Bot neu gestartet) — "
                           "schick den Track erneut", show_alert=True)
        return
    if offer.get("dismiss"):
        await query.answer("OK")
        try:
            await query.edit_message_text("✅ Nur den Track — wie gewünscht.")
        except Exception:
            pass  # editing old messages can fail; the tap is what counts
        return
    await query.answer()
    label = (f"{offer['artist']} - {offer['album_title']}"
             + (f" ({offer['year']})" if offer.get("year") else ""))
    try:
        await query.edit_message_text(
            f"⬇️ {label[:120]} — Album-Download angenommen, "
            "läuft als Nächstes über MusicGrabber.")
    except Exception:
        pass
    job = jobs_mod.add_job(f"Album: {label[:150]}", _chat_id(update))
    job["kind"] = "album"
    job["album"] = offer
    jobs_mod.update_job(job["id"], album=offer)  # restart-safe on disk
    await context.bot_data["queue"].put(job)


async def _on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _deny(update)
        return
    text = (update.effective_message.text or "").strip()
    if not text:
        return
    if len(text) > MAX_MESSAGE_LEN:
        text = text[:MAX_MESSAGE_LEN]
    job = jobs_mod.add_job(text, _chat_id(update))
    await context.bot_data["queue"].put(job)
    stats = jobs_mod.queue_stats()
    pos = "läuft jetzt" if stats["running_job"] is None and stats["queued"] <= 1 \
        else f"Position {stats['queued']}"
    await update.effective_message.reply_text(
        f"✅ Job {job['id']} angenommen ({pos})"
    )


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def cmd_bot() -> int:
    bootstrap()
    token = _load_token()
    if not token:
        print(f"bot: kein Token gefunden.")
        print(f"  1. Bei @BotFather einen Bot anlegen (/newbot).")
        print(f"  2. Token in {_token_file()} eintragen:")
        print('       {"token": "123456:ABC-DEF..."}')
        return 1
    if not _allowlist():
        print("bot: WARNUNG — bot_allowlist ist leer, niemand ist autorisiert.")
        print("     Sende dem Bot eine Nachricht; er antwortet mit deiner Chat-ID.")
    missing = [k for k, v in fetch.tool_versions().items() if not v]
    if missing:
        print(f"bot: fetch tools fehlen: {', '.join(missing)} — erst install.bat laufen lassen")
        return 1

    app = (
        Application.builder()
        .token(token)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(CommandHandler("help", _cmd_help))
    app.add_handler(CommandHandler("status", _cmd_status))
    app.add_handler(CommandHandler("asis", _cmd_asis))
    app.add_handler(CallbackQueryHandler(_on_asis_callback, pattern=r"^asis:"))
    app.add_handler(CallbackQueryHandler(_on_album_callback, pattern=r"^album:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_message))

    print("bot: starte long polling …")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
    return 0
