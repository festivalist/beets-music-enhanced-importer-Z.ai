# musik — automated MusicBrainz tagging for large music libraries

`musik` turns a large, messy music collection into a cleanly tagged, consistently
organized library: every album is identified against **MusicBrainz** (with
**Discogs** as fallback), renamed, moved into a predictable folder layout, and
enriched with cover art and genres. It runs unattended — no per-album clicking —
while staying deliberately *not blind*: anything it cannot confidently identify
is queued for a quick batch review instead of being silently mis-tagged.

Built on [beets](https://beets.io) with a custom decision layer; the result is a
clean base for any player (Plexamp/Jellyfin/foobar …).

## Why musik

Real-world music folders contain albums, EPs, compilations, vinyl rips, one-file
live recordings, playlists, and "Top 100" containers holding a hundred different
artists. And when you have 1,000+ albums, *one prompt per album is not a
workflow*. So musik:

- **auto-accepts minor things** — reissue/remaster years, subtitle variants
  ("Djam Leelii: The Adventurers"), artist-credit formatting differences
  (`5MIINUST` vs `5MIINUST, nublu`), small spelling deviations, 1-second
  duration drift, a bonus file more or less than the release tracklist;
- **never accepts wrong things** — wrong artist/album candidates and releases
  the sources don't know yet (brand-new scene/0-day rips) go to a review queue;
- **never lets rate limiting corrupt results** — a failed lookup is recorded
  and retried, never silently imported untagged;
- **deletes nothing** — duplicate losers and unmapped leftover files are
  archived to a trash folder with a manifest for audit/restore.

## Requirements

- Windows 10/11 (installer is Windows-first; the tool itself is plain Python)
- Python 3.10 or newer (the installer sets this up if missing)
- MusicBrainz is free; a Discogs **personal access token** is optional but
  recommended (get one: https://www.discogs.com/settings/developers → *Generate
  new token*, scope `database`)

## Install (one click)

1. Download/clone this repo and extract it anywhere (e.g. `C:\Tools\musik`).
2. Double-click **`install.bat`**.
3. Day-to-day: drag a folder of new music onto **`import-here.bat`**.

The installer: finds or installs Python, creates a local `.venv`, installs
beets and dependencies, downloads the `fpcalc` acoustic fingerprinter
(chromaprint), and starts the **setup wizard** — which asks for your music
library root and (optionally) your Discogs token, then writes `config.yaml`
for *your* machine. Your config and token stay local; nothing personal is
committed or sent anywhere.

Manual alternative:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
:: download fpcalc (chromaprint) manually into bin\fpcalc.exe, then:
.venv\Scripts\python musik.py setup
```

**Linux / Raspberry Pi:** run `bash install.sh` instead — same steps
(Python ≥ 3.10, `.venv`, all dependencies, self test, setup wizard) plus a
`musik-bot.service` systemd unit for the Telegram bot. Native tools come
from apt (`ffmpeg`, `libchromaprint-tools`, `flac`).

## Remote downloads: link in, album in the library

Send a Spotify or YouTube link — from anywhere, no local network needed —
and the pipeline does the rest: download → tag via the full musik chain
(MusicBrainz etc.) → file into the library → optional Plex scan so it
shows up in Plexamp. No manual steps in between.

```
musik.bat fetch --import "https://open.spotify.com/album/4yP0..."   :: album
musik.bat fetch --import "https://open.spotify.com/playlist/37i..." :: playlist
musik.bat fetch --import "https://youtu.be/dQw4w9WgXcQ"             :: single track
musik.bat fetch --import "Rick Astley - Never Gonna Give You Up"    :: free-text search
musik.bat fetch --self-test                                        :: tool check
```

Routing: **Spotify** links go through *spotDL*, **YouTube/YT-Music** links
and free-text searches through *SomeDL* (both pinned in
`requirements.txt`). Downloads land as `.m4a` in `<library>\_incoming\`,
one folder per link; albums import as MusicBrainz-matched albums,
playlists split into `Singles\`, one-track links become singletons.
Failed tracks are retried automatically; whatever remains is reported.

### The Telegram bot (`musik bot`)

1. Create a bot with [@BotFather](https://t.me/BotFather) (`/newbot`), put
   its token into `telegram_token.json` next to `config.yaml`:
   `{"token": "123456:ABC-DEF..."}` (the setup wizard can store it too).
2. Start the bot: **`musik-bot.bat`** (Windows) or `systemctl start
   musik-bot` (Pi). It uses long polling — no port forwarding, no tunnel.
3. Send it any message; the denial reply contains your chat id. Put that
   id into `config.yaml` under `musik: bot_allowlist: [123...]` and
   restart the bot.
4. Now send links: you get progress updates (`⬇️ download`, `📦 N tracks`,
   import) and a summary per album. `/status` shows queue and history.

This bot is **independent** of the ZCode desktop Telegram relay — it runs
as its own service with its own token.

### Plex / Plexamp refresh (optional)

Add to `config.yaml` (under `musik:`):

```yaml
    plex:
        url: http://plexpi:32400
        token: YOUR-X-PLEX-TOKEN
        section: Musik          # optional; first music library if omitted
```

After each successful import the bot triggers a section scan; the
"available in Plexamp" follow-up follows with the next Plexamp sync.

### Runbook

- **`YT-DLP download error` on individual tracks**: the #1 cause is a
  missing **Deno** runtime — yt-dlp needs it to solve YouTube's JS
  challenges on certain videos, and without it those same videos fail
  every run. The installers fetch Deno automatically; manual fix:
  `.venv\Scripts\python -m spotdl --download-deno`. Failed tracks are
  retried automatically: 3 rounds, 60 s cooldown, single-threaded, only
  the failed tracks, with alternate audio providers
  (`musik: fetch:` in config.yaml tunes all of this).
- **Mass breakage** (nearly all tracks fail): YouTube changed something —
  update the pinned tools:
  `.venv\Scripts\python -m pip install -U spotdl somedl` (they carry
  their own `yt-dlp`).
- **Bot detection on unattended servers**: if downloads keep failing,
  exporting YouTube cookies helps (yt-dlp Netscape format); weigh the
  risk to the account. Not configured by default.
- **Big playlists**: SomeDL sleeps between requests; expect a playlist of
  hundreds of tracks to take a while. Every job is capped at 60 minutes.
- **Logs**: `reports\fetch\<job>.log` (full downloader output),
  `.errors` (failed tracks), state of the queue in `state\bot-jobs.json`.
- **Duplicates**: if a better copy (e.g. FLAC) is already in the library,
  the download loses the quality comparison and is archived to
  `_trash\duplicate\` — the bot message says so.


## Usage

All commands run from the tool folder via the `musik.bat` shim. Where
`<folder>` appears, use any source folder of incoming music — the match is a
prefix, so a whole drive path or a single album folder both work.

**Drag & drop:** the quickest way is to drag a folder of new music onto
**`import-here.bat`** (in the tool folder) — several folders at once work
too and are processed one after another. It runs the full cycle and pauses
at the end — scan → import → interactive review → cleanup → report. For
hard-doubt albums it stops and asks per unit with the usual beets-style
options: accept a candidate, search again, apply a MusicBrainz ID,
import as-is anyway, skip, ignore forever, or abort the rest. Every imported
album prints a **track-by-track protocol** (`[direct]` = exact MusicBrainz
match, `[enhanced]` = matched via the forgiving rules, `[unmapped]` =
leftover file archived to the trash) plus an album summary line like
`14 file(s): 12 direct MusicBrainz match(es), 2 enhanced-acceptance`. After
the run, the **cleanup step** archives the leftover packaging (.nfo/.sfv/.m3u)
of imported albums to `_trash\source-cleanup\` and deletes folders left
empty — including the dropped root folder once nothing at all remains in it
(folders whose albums still wait in review keep their audio and are never
touched). Finally a **session summary** totals the whole action, broken
down by release kind and how each was decided:

```
kind    direct  enhanced  own-tags  undecided  deferred  duplicate  failed  total
album       15         3         1          1         0          0      0     20
ep           3         0         0          2         0          0      0      5
files imported: 318, unmapped archived: 1
```

(EPs/singles come from the matched MusicBrainz `albumtype`; own-tag imports
use a track-count heuristic — 1 track = single, 2–6 = EP, more = album;
one-file live sets count as `mix`.) The same table is written to
`reports\session-report.md`, including the names of anything still undecided.

Command line equivalent:

```bat
musik.bat scan --root "D:\Incoming\2026-09-02"
                                          :: classify that folder into units (read-only)
musik.bat import --dry-run                :: lookups + decisions only, nothing moves
musik.bat import                          :: the real thing: tag, move, fetch art, write DB
musik.bat import --limit 10               :: first 10 pending units only
musik.bat import --unit "D:\Incoming\2026-09-02"
                                          :: import exactly one source folder (prefix match)
musik.bat retry                           :: re-run units whose lookups failed
musik.bat retry --include-unmatched       :: also re-attempt "no match found" units
musik.bat apply                           :: process decisions you made in reports\review.csv
musik.bat review --unit "D:\Incoming\2026-09-02"
                                          :: interactive decisions for doubtful units:
                                          ::    [A] accept best  [2]/[3] candidate 2/3
                                          ::    [O] override search  [I] apply MBID
                                          ::    [W] import as-is  [S] skip  [X] ignore  [Q] abort
musik.bat cleanup --root "D:\Incoming\2026-09-02"
                                          :: archive leftovers of imported albums to
                                          ::    _trash\source-cleanup, remove emptied folders
                                          ::    (--dry-run to preview)
musik.bat asis --unit "D:\Incoming\2026-09-02"
                                          :: explicit: file review units whose own tags are
                                          ::    complete using those tags (no MB match needed)
musik.bat report --verify                 :: reports + library sanity checks
musik.bat dedupe --dry-run                :: duplicate cleanup preview (quality-based)
```

Typical per-batch workflow for a folder of new music:

```bat
musik.bat scan --root "D:\Incoming\2026-09-02"
musik.bat import --dry-run --unit "D:\Incoming\2026-09-02"
musik.bat import --unit "D:\Incoming\2026-09-02"
musik.bat review --unit "D:\Incoming\2026-09-02"    :: optional, interactive
musik.bat asis --unit "D:\Incoming\2026-09-02"      :: optional
musik.bat cleanup --root "D:\Incoming\2026-09-02"   :: archive junk, remove emptied folders
musik.bat report --verify
```

Finished albums land in your library root as `<Artist>\<year - Album>\<disc-><track> <title>`,
with `Singles\` and `Compilations\` branches — all configurable in `config.yaml`.

## Library care & discovery

Once the importing is done, these commands keep the library healthy and
help it grow. Everything is **report-only by default** — writing happens
only with `--fix` / `--apply`.

```bat
musik.bat snapshot                          :: zip up DB+config+state+tokens
                                            ::    into <library>\_backups (rotating,
                                            ::    last 10 by default); --list shows them
musik.bat doctor                            :: health check: dead DB rows, orphan files,
                                            ::    FLAC bitrot decode test, missing art/genre,
                                            ::    long paths -> reports\doctor-report.md
musik.bat doctor --quick                    :: skip files already decode-tested
musik.bat doctor --limit 100                :: decode-test only ~100 files (spot check)
musik.bat doctor --fix                      :: remove dead rows, backfill art/genre
musik.bat stats                             :: totals, formats, decades, top artists,
                                            ::    monthly additions -> library-stats.md
musik.bat similar                           :: artists you don't have yet, based on
                                            ::    ListenBrainz similarity of your MB IDs
                                            ::    -> similar-artists.md (--refresh re-queries)
musik.bat releases                          :: new album/EP release groups of your library
                                            ::    artists since the last run -> new-releases.md
musik.bat retag                             :: re-check as-is albums against the sources
                                            ::    (report only) -> retag-report.md
musik.bat dedupe --fingerprint              :: same recording under different metadata
                                            ::    (AcoustID), report only; --apply trashes
                                            ::    the lower-quality copy
```

Notes:

- **Plexamp/Plex**: the library folder is meant to be used directly as a
  Plex/Plexamp music source. The layout (`Artist\year - Album\`, embedded
  artwork, ReplayGain tags) is Plex-friendly; after an import session,
  let Plex scan the folder so new albums show up on the RPi endpoint.
- ReplayGain (`replaygain` plugin, bundled `bin\ffmpeg.exe`) is applied
  automatically to future imports and was backfilled once over the whole
  library; VLC and Plexamp both pick the tags up. `embedart` embeds the
  fetched cover into every file at import time.
- FLAC integrity is checked by actually decoding every file against its
  internal MD5 — the first full `doctor` run takes a while, `--quick`
  (mtime/size cache) is what the monthly routine uses.

## How decisions are made

Identification runs as a **priority chain** — the first tier that accepts a
unit wins:

1. **MusicBrainz strict** — album title, artist, track titles and durations
   all agree directly;
2. **MusicBrainz enhanced** — the same release behind minor noise: small
   spelling deviations, artist-credit formatting (`5MIINUST` vs
   `5MIINUST, nublu`), reissue years, subtitle variants, 1–3 track-count
   differences (leftover files are archived to `_trash\unmapped-track\`),
   duration drift up to 10 s, vinyl side numbering;
3. **own metadata** — when the sources *genuinely don't know the release*
   (no candidates at all, or every candidate is unrelated beyond distance
   0.35), the files' own tags become the source: they must be complete and
   consistent, and for albums the folder-name parse must agree with the
   tags (two independent presentations corroborating each other). Typical
   beneficiaries: 0-day/scene WEB releases MusicBrainz hasn't indexed yet,
   and DJ mixes/live sets that never will be. Units imported this way are
   marked `asis` and can be re-tagged once MusicBrainz catches up;
4. **review queue** — everything else: contradictory tags/folder names,
   middle-band candidates (distance 0.25–0.35, where MusicBrainz might
   still know the release), untagged files.

A lookup that *failed* (rate limit, network) never reaches tiers 3/4 as a
"no match" — failed units are deferred and retried automatically within
the run. The folder-name year (e.g. `0701. Slint - Spiderland (1991)`)
vetoes candidates that look like a *different recording* (live/broadcast/
demo-style tokens) or drop part of the album title.

Review units can be resolved three ways: the interactive `review` command,
the `review.csv` batch flow, or the explicit `asis` command — plus the
automatic tier 3 above for the self-evident cases.

### 0-day material and the asis command

Brand-new scene/WEB releases are often **not in MusicBrainz or Discogs yet**,
even though their own tags are good. Those are handled automatically by
priority tier 3 (see *How decisions are made*): when the sources have no
usable candidate and the tags are complete, consistent and agree with the
folder name, the unit is imported on its own tags and marked `asis`. For
units the automatic rule rejects (contradictory tags, middle-band
candidates), `musik.bat asis --unit <folder>` remains the explicit escape
hatch, and `review` / `review.csv` + `apply` the deliberate routes.

### Mixed batches: the import playbook

Large mixed drops (albums + chart dumps + label compilations + vintage
collections) import best in phases — different material needs different
sources and different modes:

| Phase | Material | Mode | Sources |
|---|---|---|---|
| 1 | artist albums / EPs / singles | normal import | all |
| 2 | VA compilations (Ministry of Sound, The Annual, …) | normal import — the **VA rule** handles them | musicbrainz, discogs |
| 3 | chart / "best new" dumps (many artists, no real album) | singleton import (`--sources musicbrainz,beatport4` — beatport4 for electronic material) | per flag |
| 4 | vintage / mixed-tag collections | `tools\pretag_from_folder.py <root> --unify-album` then `musik.bat asis --pending --unit <root>` | none |

Rules baked in (no manual work needed):

- **VA rule** (decider): album units without a meaningful release credit
  (albumartist missing/"Various" and ≥3 distinct track artists) skip the
  artist comparison — VA and DJ-mixed releases are credited to "Various
  Artists"/the mixer by design. Identity rests on album title (loosened to
  0.15), a near-complete track mapping, year and the distance cap.
- **Split rule** (scan): loose multi-artist folders split into singletons
  only when their album tags are missing or inconsistent. A folder with
  one consistent album tag across many artists is a real compilation and
  imports as an album.
- **`--sources` flag** (`import`/`retry`): limits metadata plugins per run,
  e.g. `--sources musicbrainz,beatport4`. Discogs is excluded from
  singleton passes automatically when you pass sources without it — its
  release-level matches would write album data into singles.
- **Corrupt gate** (scan): files mutagen cannot parse are excluded from
  units and archived to `_trash\corrupt` after their unit's import.
- **`beatport4` token** (preflight): an expired access token is refreshed
  automatically from the stored refresh token before the import starts
  (`tools\beatport_refresh.py` does the same standalone).
- **`report --verify --fix`**: removes library DB rows whose files are
  gone (phantom rows from playlist-referenced files).
- **`tools\va_asis_prepare.py`**: last step for stubborn VA-album reviews —
  completes tags (albumartist=Various Artists, per-CD album tag variants)
  so `asis --pending` can file them.

## Rate limiting & reliability

- MusicBrainz is throttled to its mandated 1 request/second; Discogs,
  AcoustID and last.fm calls are throttled too, with automatic backoff and
  retries on 429/5xx.
- The engine distinguishes **"no match found"** from **"request failed"** —
  a rate-limited lookup is never silently imported untagged; affected units
  are deferred and retried automatically within the run.
- Runs are **resumable**: progress is saved per unit, so Ctrl+C at any point
  and re-run the same command.

## Files and directories (defaults)

| Path | Purpose |
|---|---|
| `install.bat` / `install.ps1` | one-click installer (Python, venv, deps, fpcalc, setup) |
| `musik.bat` | command shim (`musik.bat <command> …`) |
| `import-here.bat` | drag & drop a folder onto this to run the full import cycle |
| `config.yaml` | generated by `setup`; your paths and all tuning knobs |
| `discogs_token.json` | your Discogs token (written by `setup`, local only) |
| `.venv\` | the Python environment the installer creates |
| `bin\fpcalc.exe` | acoustic fingerprinter (downloaded by the installer) |
| `bin\flac.exe` | FLAC decoder for `doctor` bitrot tests (downloaded by the installer) |
| `bin\ffmpeg.exe` | loudness analysis for ReplayGain (downloaded by the installer) |
| `state\state.json` | per-unit progress; crash-safe, resumable |
| `reports\` | `import-report.md`, `dry-run-report.md`, `scan-report.md`, `review.csv`, `unidentified.csv`, `doctor-report.md`, `library-stats.md`, `similar-artists.md`, `new-releases.md`, `retag-report.md` |
| `<library>\_trash\` | displaced files + `manifest.csv` for audit/restore |
| `<library>\_backups\` | `musik snapshot` ZIPs (rotating; move somewhere safe!) |
| `<library>\beets-library.db` | the beets database |

## Tuning

All thresholds live in `config.yaml` under `musik:`:

| Key | Default | Meaning |
|---|---|---|
| `auto_accept_distance` | 0.25 | total-distance cap for auto-accept |
| `review_candidates` | 3 | candidates recorded per review row |
| `retry_rounds` | 2 | automatic retry rounds for failed lookups |
| `retry_cooldown_seconds` | 20 | pause between retry rounds |
| `trash_dir` | `<library>\_trash` | where displaced files go |
| `backup_dir` | `<library>\_backups` | where `musik snapshot` stores its ZIPs |
| `backup_keep` | 10 | how many snapshots to keep (oldest rotated away) |

Beets-level knobs (`match:`, `paths:`, `fetchart:` …) are documented in the
[beets docs](https://beets.readthedocs.io/); the generated config already
contains a tuned starting point.

## Troubleshooting

- **"no config.yaml found"** → run `musik.bat setup`.
- **`discogs=FAIL` in the preflight line** → the token is missing/invalid;
  get a personal access token and re-run `setup` (MusicBrainz-only operation
  works fine without it).
- **Acoustic fingerprinting disabled** → `bin\fpcalc.exe` is missing; rerun
  the installer or download chromaprint manually.
- **Albums without cover art** → fetchart found no source; re-run
  `.venv\Scripts\python -m beets fetchart -f` later.
- **MusicBrainz 503s in the preflight line** → transient service load; the
  built-in retries handle it, nothing to do.

## License

[MIT](LICENSE) — uses [beets](https://github.com/beetbox/beets) (GPL-2.0 as an
installed dependency, not bundled) and chromaprint's `fpcalc` (downloaded at
install time, not bundled).
