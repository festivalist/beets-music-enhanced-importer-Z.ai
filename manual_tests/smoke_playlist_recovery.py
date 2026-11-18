# -*- coding: utf-8 -*-
"""Smoke test for Story 2.7: fetch playlist recovery + real names.

Run:  python manual_tests/smoke_playlist_recovery.py
Netzfrei (Story 6.6 suite): Spotify-oEmbed and Plex are mocked; the live
oEmbed probe was done during the story (37i9dQZF1DXcBWIGoYBM5M ->
"Today's Top Hits"). Matrix per ToDo 2.7: Spotify/YT link (names),
Interrupt+Recovery (bounce + ingest plans + resume), renaming idempotent
(re-upload replaces via stable m3u path).
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp(prefix="smoke-plrec-")
st_dir = os.path.join(tmp, "state")
os.makedirs(st_dir)

from musik import paths as paths_mod  # noqa: E402

_real_musik_config = paths_mod.musik_config


def fake_cfg():
    cfg = dict(_real_musik_config())
    cfg["state_dir"] = st_dir
    return cfg


paths_mod.musik_config = fake_cfg

import musik.bot as B  # noqa: E402
import musik.fetch as F  # noqa: E402
import musik.jobs as J  # noqa: E402
import musik.playlists as P  # noqa: E402

incoming = os.path.join(tmp, "incoming")
os.makedirs(incoming)


def fake_incoming():
    return incoming


paths_mod.incoming_dir = fake_incoming
F.incoming_dir = fake_incoming

# ---------------------------------------------------------------- 1) marker
job_dir = os.path.join(incoming, "fetch-20261118-120000-spotify-37i9dQZF1")
os.makedirs(job_dir)
F.write_context(job_dir, "spotify",
                "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
ctx = F.read_context(job_dir)
assert ctx["kind"] == "spotify" and "37i9dQZF1DXcBWIGoYBM5M" in ctx["query"]
for name in ("A - Eins.m4a", "B - Zwei.m4a"):
    with open(os.path.join(job_dir, name), "w") as fh:
        fh.write("x")
fj = F.job_from_dir(job_dir)
assert fj.kind == "spotify" and fj.query == ctx["query"], (fj.kind, fj.query)
assert fj.job_id == os.path.basename(job_dir)
assert [os.path.basename(f) for f in fj.files] == ["A - Eins.m4a", "B - Zwei.m4a"]
print("1) context marker + job_from_dir OK")

# pre-marker folder: kind from dir name, query unrecoverable
old_dir = os.path.join(incoming, "fetch-20261117-090000-youtube-PLxyz")
os.makedirs(old_dir)
with open(os.path.join(old_dir, "C - Drei.m4a"), "w") as fh:
    fh.write("x")
fj_old = F.job_from_dir(old_dir)
assert fj_old.kind == "youtube" and fj_old.query == "", (fj_old.kind, fj_old.query)
print("   pre-marker fallback (kind from dir name) OK")

# ------------------------------------------------- 2) prepare: gates+names
oembed_calls = []


def fake_oembed(url):
    oembed_calls.append(url)
    return "Klare Kante"


P._spotify_oembed_name = fake_oembed

# sidecar wins, oEmbed not consulted; sidecar evidence also works without
# a query (pre-marker resume)
with open(os.path.join(old_dir, "Meine Liste.m3u8"), "w", encoding="utf-8") as fh:
    fh.write("#EXTM3U\n#EXTINF:200,C - Drei\nC - Drei.m4a\n")
specs = P.prepare(fj_old)
assert specs and specs[0]["name"] == "Meine Liste", specs
assert oembed_calls == [], oembed_calls
print("2a) sidecar evidence without query (pre-marker resume) OK")

# album link, no sidecar -> no playlist
alb_dir = os.path.join(incoming, "fetch-20261118-130000-spotify-AlbumX")
os.makedirs(alb_dir)
with open(os.path.join(alb_dir, "A - Track.m4a"), "w") as fh:
    fh.write("x")
fj_alb = F.job_from_dir(alb_dir)
F.write_context(alb_dir, "spotify", "https://open.spotify.com/album/abc123")
fj_alb.query = "https://open.spotify.com/album/abc123"
assert P.prepare(fj_alb) is None
print("2b) album link spawns no playlist OK")

# spotify playlist without sidecar: real name via oEmbed, mtime order
pl_dir = os.path.join(incoming, "fetch-20261118-140000-spotify-37i9dQZF1YYY")
os.makedirs(pl_dir)
files = []
for nm, age in (("b - Zwei.m4a", 300), ("a - Eins.m4a", 200)):
    p = os.path.join(pl_dir, nm)
    with open(p, "w") as fh:
        fh.write("x")
    os.utime(p, (age, age))
    files.append(p)


class SpotifyJob:
    job_id = os.path.basename(pl_dir)
    job_dir = pl_dir
    query = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
    kind = "spotify"
    files = files


F.write_context(pl_dir, "spotify", SpotifyJob.query)


specs = P.prepare(SpotifyJob)
assert specs and specs[0]["name"] == "Klare Kante", specs
assert [e["file"] for e in specs[0]["entries"]] == ["a - Eins.m4a", "b - Zwei.m4a"]
assert oembed_calls == [SpotifyJob.query]
print("2c) spotify fallback name via oEmbed + mtime order OK")

# ------------------------------------------------ 3) m3u path is stable
P.m3u_dir = lambda: os.path.join(tmp, "m3u")
os.makedirs(os.path.join(tmp, "m3u"), exist_ok=True)
P._lib = lambda: None
lib_items = [
    {"id": 1, "path": os.path.join(tmp, "lib", "01 Eins.m4a"),
     "title": "Eins", "artist": "A", "albumartist": "A"},
    {"id": 2, "path": os.path.join(tmp, "lib", "02 Zwei.m4a"),
     "title": "Zwei", "artist": "B", "albumartist": "B"},
    # stale row with a dead staging path (KK-GOTCHA): must never match
    {"id": 3, "path": os.path.join(incoming, "fetch-x", "Eins.m4a"),
     "title": "Eins", "artist": "A", "albumartist": "A"},
]
for it in lib_items:
    if os.path.isfile(it["path"]):
        continue
    if "fetch-x" not in it["path"]:
        os.makedirs(os.path.dirname(it["path"]), exist_ok=True)
        with open(it["path"], "w") as fh:
            fh.write("x")
P._items_since = lambda ids: [it for it in lib_items
                              if os.path.isfile(it["path"])]
stale = [it for it in P._items_since(None) if "fetch-x" in it["path"]]
assert stale == [], stale
print("3a) stale rows with dead paths filtered OK")


class BuildJob:
    job_id = SpotifyJob.job_id
    job_dir = pl_dir
    query = SpotifyJob.query


entries = [{"file": "a - Eins.m4a", "artist": "A", "title": "Eins"},
           {"file": "b - Zwei.m4a", "artist": "B", "title": "Zwei"}]
states = P.build(BuildJob(), [{"name": "Klare Kante", "entries": entries}],
                 ids_before=set())
m3u_v1 = states[0]["m3u"]
assert os.path.isfile(m3u_v1)

# same job re-built under a DIFFERENT (renamed) spec: same m3u file, so a
# Plex re-upload REPLACES instead of spawning a second playlist
states = P.build(BuildJob(), [{"name": "Klare Kante (2026)", "entries": entries}],
                 ids_before=set())
assert states[0]["m3u"] == m3u_v1, (states[0]["m3u"], m3u_v1)
print("3b) rename keeps the m3u path stable OK")

# --------------------------------------- 4) upload rename of spotify-<id>
plex_calls = []


def fake_upload(m3u, title=None):
    plex_calls.append(title)
    return True, f"Plex-Playlist „{title}“: 2 Track(s) verfügbar"


import musik.plex as plex_mod  # noqa: E402

plex_mod.upload_playlist = fake_upload

legacy = {
    "job_id": "fetch-20261101-100000-spotify-2mLkxxxxxx",
    "job_dir": os.path.join(incoming, "fetch-20261101-100000-spotify-2mLkxxxxxx"),
    "state_file": "fetch-20261101-100000-spotify-2mLkxxxxxx",
    "name": "spotify-2mLkxxxxxx",
    "query": "https://open.spotify.com/playlist/2mLkxxxxxx",
    "tracks": [{"file": "a - Eins.m4a", "artist": "A", "title": "Eins",
                "dest": lib_items[0]["path"]}],
    "m3u": m3u_v1,
}
P._save_state(legacy)
msgs = P.upload([legacy])
assert any("umbenannt" in m for m in msgs), msgs
assert legacy["name"] == "Klare Kante"
assert legacy["m3u"] == m3u_v1  # same file -> Plex replaces
assert plex_calls == ["Klare Kante"], plex_calls
stored = P._load_state(legacy["state_file"])
assert stored["name"] == "Klare Kante"
print("4) legacy spotify-<id> renamed once, upload replaces OK")

# second upload: renamed already -> no second oEmbed call (idempotent)
oembed_calls.clear()
msgs = P.upload([legacy])
assert oembed_calls == [], oembed_calls
print("   rename idempotent across repeat uploads OK")

# ------------------------------------------------------------ 5) by job id
assert [pl["job_id"] for pl in P.state_for_job(legacy["job_id"])] == \
    [legacy["job_id"]]
multi = dict(legacy, job_id=f"{legacy['job_id']}--Extra", state_file="extra-x",
             name="Extra")
P._save_state(multi)
assert len(P.state_for_job(legacy["job_id"])) == 2
assert P.state_for_job("fetch-does-not-exist") == []
print("5) state_for_job (exact + multi-sidecar variants) OK")

# ------------------------------------- 6) recover_interrupted: the bounce
def seed(jobs):
    with open(os.path.join(st_dir, "bot-jobs.json"), "w", encoding="utf-8") as fh:
        json.dump(jobs, fh, ensure_ascii=False)


def base_job(jid, status="running", **extra):
    d = {"id": jid, "text": "https://open.spotify.com/playlist/xyz",
         "chat_id": 1, "status": status, "created": 1000.0,
         "started": 1001.0, "finished": None, "summary": ""}
    d.update(extra)
    return d


live_staging = os.path.join(incoming, "fetch-20261118-150000-spotify-live")
os.makedirs(live_staging)
gone_staging = os.path.join(incoming, "fetch-20261118-160000-spotify-gone")
pending_pl = {"job_id": os.path.basename(gone_staging), "name": "Klare Kante",
              "tracks": [{"file": "a", "title": "Eins", "dest": "x"}]}
uploaded_pl = dict(pending_pl, job_id="uploaded-job")
uploaded_pl["plex"] = {"uploaded": 123.0, "message": "ok"}
P._save_state(pending_pl)
P._save_state(uploaded_pl)

P.state_for_job_orig = P.state_for_job


def fake_state_for_job(job_id):
    if job_id == os.path.basename(gone_staging):
        return [pending_pl]
    if job_id == "uploaded-job":
        return [uploaded_pl]
    return P.state_for_job_orig(job_id)


P.state_for_job = fake_state_for_job

seed([
    base_job("live", staging_dir=live_staging),
    base_job("pending", staging_dir=gone_staging),
    base_job("uploaded", staging_dir=os.path.join(incoming, "fetch-nope")),
    base_job("album", kind="album", staging_dir=live_staging),
    base_job("lost"),
    base_job("q1", status="queued"),
    base_job("done", status="done", text="old"),
])
killed, requeued = J.recover_interrupted()
assert [j["id"] for j in killed] == ["uploaded", "album", "lost"], killed
assert [j["id"] for j in requeued] == ["live", "pending", "q1"], requeued
stored = {j["id"]: j for j in J.load_jobs()}
for jid in ("live", "pending"):
    assert stored[jid]["status"] == "queued" and stored[jid]["resume"] is True
    assert "ohne erneuten Download" in stored[jid]["summary"]
for jid in ("uploaded", "album", "lost"):
    assert stored[jid]["status"] == "error"
    assert "Link erneut schicken" in stored[jid]["summary"]
assert stored["done"]["status"] == "done"
print("6) recover_interrupted: bounce (staging/pending playlist), kill (lost/managed) OK")

P.state_for_job = P.state_for_job_orig

# ------------------------------------- 7) resume execution (decision paths)
# the interrupted job's staging holds files + its context marker
F.write_context(live_staging, "spotify",
                "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
with open(os.path.join(live_staging, "A - Eins.m4a"), "w") as fh:
    fh.write("x")
seed([base_job("live", status="queued", resume=True,
               staging_dir=live_staging),
      base_job("pending", status="queued", resume=True,
               staging_dir=gone_staging),
      base_job("lost", status="queued", resume=True,
               staging_dir=os.path.join(incoming, "fetch-lost-lost"))])

run_fetch_calls = []
real_run_fetch = F.run_fetch


def fake_run_fetch(inputs, resume_dir=None, **kw):
    run_fetch_calls.append((list(inputs), resume_dir))
    fj = F.FetchJob(job_id=os.path.basename(resume_dir), kind="spotify",
                    tool="spotdl", query=inputs[0], job_dir=resume_dir,
                    log_path=os.path.join(tmp, "fake.log"))
    fj.outcomes = [("auto", "A - Eins")]
    return [fj]


F.run_fetch = fake_run_fetch


def fake_import(fjob):
    fjob.playlists = []
    return []


F._import_job = fake_import

sent: list[str] = []
B.plex_mod.refresh_library = lambda: (True, "Plex aktualisiert")
msgs = B._deliver_fetch(fake_run_fetch(["q"], resume_dir=live_staging), sent.append)
assert len(msgs) == 1 and msgs[0].startswith("q"), msgs
print("7a) _deliver_fetch shared path OK")

# resume with staging: continues download IN PLACE (no new job dir)
B._execute_fetch_resume(stored["live"], sent.append)
call = run_fetch_calls[-1]
assert call[1] == live_staging, call          # same dir, no re-request
assert "37i9dQZF1DXcBWIGoYBM5M" in call[0][0]  # marker query
stored = {j["id"]: j for j in J.load_jobs()}
assert stored["live"]["status"] == "done", stored["live"]
assert any("nicht erneut heruntergeladen" in m for m in sent)
print("7b) resume with staging: run_fetch(resume_dir=staging) OK")

# resume without staging but pending playlist state: upload only
B.plex_mod.upload_playlist = fake_upload
B.playlists_mod.state_for_job = fake_state_for_job
B._execute_fetch_resume(stored["pending"], sent.append)
stored = {j["id"]: j for j in J.load_jobs()}
assert stored["pending"]["status"] == "done", stored["pending"]
assert any("Playlist nachgeholt" in m for m in sent), sent
print("7c) resume without staging: playlist upload only OK")

# resume with nothing left: honest error
B._execute_fetch_resume(stored["lost"], sent.append)
stored = {j["id"]: j for j in J.load_jobs()}
assert stored["lost"]["status"] == "error"
assert any("erneut schicken" in m for m in sent)
print("7d) resume with nothing left: honest error OK")

B.playlists_mod.state_for_job = P.state_for_job_orig

# --------------------------------------- 8) ingest plans for fetch dirs
import musik.ingest as ing  # noqa: E402

ing._mg_playlist_plans = lambda root: []
plans = ing._fetch_playlist_plans(incoming)
by_id = {p["job"].job_id: p for p in plans}
assert os.path.basename(job_dir) in by_id, sorted(by_id)
plan = by_id[os.path.basename(job_dir)]
assert plan["specs"][0]["entries"], plan
assert os.path.basename(pl_dir) in by_id     # spotify fallback with oEmbed
assert os.path.basename(alb_dir) not in by_id  # album link: no plan
print("8) ingest collects fetch playlist plans (albums excluded) OK")

# run_fetch refuses resume with multiple inputs
try:
    real_run_fetch(["https://open.spotify.com/playlist/x",
                    "https://youtu.be/x"], resume_dir=job_dir)
    raise SystemExit("resume with 2 inputs must fail")
except ValueError:
    print("9) resume_dir+multi-input guard OK")

print("ALL SMOKE TESTS PASSED")
