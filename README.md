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
| `state\state.json` | per-unit progress; crash-safe, resumable |
| `reports\` | `import-report.md`, `dry-run-report.md`, `scan-report.md`, `review.csv`, `unidentified.csv` |
| `<library>\_trash\` | displaced files + `manifest.csv` for audit/restore |
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
