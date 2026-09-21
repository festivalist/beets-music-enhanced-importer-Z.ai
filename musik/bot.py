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
    "• oder Suchtext: „artist - title“\n\n"
    "Ich lade die Tracks herunter, tagge und importiere sie in die "
    "Musikbibliothek und melde mich, wenn sie fertig sind.\n\n"
    "/asis — liegengeschlafene Einheiten (Review etc.) auflisten und "
    "per Knopfdruck auf eigene Tags importieren\n"
    "/status — Warteschlange und letzte Ergebnisse"
)


# --------------------------------------------------------------------------
# worker (runs in a thread; one job at a time)
# --------------------------------------------------------------------------

def _execute_job(job: dict, send) -> None:
    """Run one job end to end; `send` delivers progress messages."""
    jobs_mod.update_job(job["id"], status="running", started=time.time())
    if job.get("kind") == "asis":
        _execute_asis(job, send)
        return
    query = job["text"].strip()
    print(f"bot: job {job['id']} running: {query[:120]}")
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
            summaries.append(fetch.summarize_job(fj))
            send(summaries[-1])
        jobs_mod.update_job(job["id"], status="done", finished=time.time(),
                            summary="\n—\n".join(summaries)[:1500])
        print(f"bot: job {job['id']} done")
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


def _run_job(job: dict, app, loop) -> None:
    chat_id = job["chat_id"]

    def send(text: str) -> None:
        try:
            fut = asyncio.run_coroutine_threadsafe(
                app.bot.send_message(chat_id=chat_id, text=text[:4000]), loop
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


async def _cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        await _deny(update)
        return
    stats = jobs_mod.queue_stats()
    lines = []
    if stats["running_job"]:
        r = stats["running_job"]
        lines.append(f"🔄 läuft: {r['text'][:80]}")
    else:
        lines.append("💤 gerade läuft nichts")
    lines.append(f"⏳ in Warteschlange: {stats['queued']}")
    for j in stats["recent"]:
        icon = "✅" if j["status"] == "done" else "❌"
        head = (j.get("summary") or "").splitlines()[0][:80] if j.get("summary") else j["text"][:60]
        lines.append(f"{icon} {head}")
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
        "Playlists landen dabei Track-für-Track in ihren echten Alben.",
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_message))

    print("bot: starte long polling …")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
    return 0
