"""Remote-download toolchain (`musik fetch`).

Bridges Spotify links to spotDL and YouTube/YT-Music links (or free-text
searches) to SomeDL, both driven as pinned CLI subprocesses (see
requirements.txt — spotDL's Python API is unstable, SomeDL documents none).
Downloads land in a staging folder under the library root and are then run
through the normal scan/import pipeline.

Job layout: one flat folder per link under <library>/_incoming/. A flat
folder is exactly what scan.py expects — an album link yields consistent
album tags (one album unit, MB match), a playlist link yields mixed tags
(scan's should_split routes those to singletons).
"""

import os
import re
import shutil
import subprocess
import sys
import sysconfig
import time
from dataclasses import dataclass, field

from .paths import bootstrap, incoming_dir, reports_dir

VERSION_TIMEOUT = 60
DOWNLOAD_TIMEOUT = 3600  # per job; the bot wants bounded runs

_URL_RE = re.compile(r"https?://\S+", re.I)
_TRAIL_RE = re.compile(r"[)\].,;:!?\"'\u2019\u201d]+$")
_SPOTIFY_HOSTS = ("open.spotify.com", "spotify.link")
_YOUTUBE_HOSTS = ("youtube.com", "music.youtube.com", "youtu.be")


# --------------------------------------------------------------------------
# tool discovery (used by `musik doctor` and the fetch self-test)
# --------------------------------------------------------------------------

def _scripts_dir() -> str:
    # Inside a venv this resolves to .venv\Scripts (win) / .venv/bin (unix),
    # regardless of whether the venv is activated (musik.bat calls the venv
    # python directly, so console scripts are NOT on PATH).
    return sysconfig.get_path("scripts") or os.path.join(sys.prefix, "Scripts")


def spotdl_cmd() -> list[str] | None:
    """Invocation prefix for spotDL (module form: version-proof)."""
    return [sys.executable, "-m", "spotdl"]


def somedl_cmd() -> list[str] | None:
    """Invocation prefix for SomeDL (console script; no __main__)."""
    exe = shutil.which("somedl")
    if exe:
        return [exe]
    for cand in ("somedl.exe", "somedl"):
        path = os.path.join(_scripts_dir(), cand)
        if os.path.isfile(path):
            return [path]
    return None


def tool_versions() -> dict[str, str | None]:
    """Versions of the fetch toolchain; None = missing or broken.

    ffmpeg resolves via PATH after bootstrap() (bundled bin/ first on
    Windows, system package on the Pi).
    """
    bootstrap()
    tools = {
        "spotdl": spotdl_cmd(),
        "somedl": somedl_cmd(),
        "ffmpeg": shutil.which("ffmpeg") and ["ffmpeg"],
    }
    result: dict[str, str | None] = {}
    for name, cmd in tools.items():
        if not cmd:
            result[name] = None
            continue
        flag = "-version" if name == "ffmpeg" else "--version"
        try:
            r = subprocess.run(
                [*cmd, flag], capture_output=True, text=True,
                errors="replace", timeout=VERSION_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired):
            result[name] = None
            continue
        if r.returncode != 0:
            result[name] = None
            continue
        first = (r.stdout or r.stderr or "").strip().splitlines()
        result[name] = first[0][:80] if first else ""
    return result


# --------------------------------------------------------------------------
# link classification
# --------------------------------------------------------------------------

def _host(url: str) -> str:
    m = re.match(r"https?://([^/]+)/", url + "/", re.I)
    return (m.group(1).lower() if m else url.lower()).removeprefix("www.")


def _resolve_shortlink(url: str) -> str:
    """Follow spotify.link / youtu.be style redirects to the canonical URL."""
    if not any(h in url for h in ("spotify.link",)):
        return url
    try:
        import requests

        r = requests.get(url, timeout=20, allow_redirects=True)
        return r.url or url
    except Exception:
        return url


def classify(text: str) -> list[tuple[str, str]]:
    """Split a message (or CLI arg) into (kind, value) pairs.

    kind is 'spotify', 'youtube' or 'search'. URLs are extracted and
    trailing punctuation stripped; any leftover non-empty text becomes one
    free-text search (SomeDL query).
    """
    pairs: list[tuple[str, str]] = []
    rest = text
    for m in _URL_RE.finditer(text):
        url = _TRAIL_RE.sub("", m.group(0))
        rest = rest.replace(m.group(0), " ")
        kind = _kind_of(url)
        if kind:
            pairs.append((kind, url))
        else:
            pairs.append(("unsupported", url))
    leftover = " ".join(rest.split()).strip()
    if leftover and not pairs:
        pairs.append(("search", leftover))
    return pairs


def _kind_of(url: str) -> str | None:
    host = _host(url)
    if any(h == host or host.endswith("." + h) for h in _SPOTIFY_HOSTS):
        return "spotify"
    if any(h == host or host.endswith("." + h) for h in _YOUTUBE_HOSTS):
        return "youtube"
    return None


# --------------------------------------------------------------------------
# download orchestration
# --------------------------------------------------------------------------

@dataclass
class FetchJob:
    job_id: str
    kind: str        # spotify | youtube | search
    tool: str        # spotdl | somedl
    query: str       # original link / text
    job_dir: str
    log_path: str
    files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    returncode: int = -1
    timed_out: bool = False
    outcomes: list[tuple[str, str]] = field(default_factory=list)  # (unit status, label)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def _slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "", text)
    return s[:24]


def _new_job_dir(kind: str, query: str) -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    ident = _slug(query.rsplit("/", 1)[-1].split("?")[0]) or kind
    base = os.path.join(incoming_dir(), f"fetch-{ts}-{kind}-{ident}")
    n = 1
    while os.path.exists(base):
        n += 1
        base = os.path.join(
            incoming_dir(), f"fetch-{ts}-{kind}-{ident}-{n}"
        )
    os.makedirs(base)
    return base


def _tool_argv(job: FetchJob, errors_file: str) -> list[str]:
    if job.kind == "spotify":
        # No --archive across jobs: a track downloaded as a single before
        # must not leave a hole in an album later. Within one job dir both
        # tools skip existing files on their own (spotdl overwrite=skip,
        # somedl check_if_file_exists), which is all the retry logic needs.
        return [
            *spotdl_cmd(), "download", job.query,
            "--output", os.path.join(job.job_dir, "{artists} - {title}.{output-ext}"),
            "--format", "m4a",
            "--print-errors", "--save-errors", errors_file,
            "--threads", "4",
        ]
    # youtube link or free-text search -> SomeDL (flat default template)
    return [
        *somedl_cmd(), job.query,
        "-o", job.job_dir,
        "-f", "best/m4a",
        "--disable-report",
    ]


def _run_logged(argv: list[str], log_path: str, job: FetchJob,
                deadline_s: float | None) -> int:
    """Run a subprocess, streaming output to the log file and console."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    timed_out = False
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        log.write("$ " + " ".join(argv) + "\n")
        log.flush()
        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", env=env,
            cwd=os.path.dirname(log_path),
        )
        try:
            for line in proc.stdout or []:
                log.write(line)
                log.flush()
                print(f"  [{job.tool}] {line.rstrip()}")
                if deadline_s and time.monotonic() > deadline_s:
                    timed_out = True
                    proc.kill()
                    break
        finally:
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    job.timed_out = timed_out
    if timed_out:
        job.errors.append("job exceeded its time budget and was killed")
    return proc.returncode


def _collect(job: FetchJob, errors_file: str) -> None:
    from .scan import collect_audio_tree

    job.files = collect_audio_tree(job.job_dir)
    # spotDL's --save-errors file accumulates across retry rounds; count
    # unique lines so repeated failures don't inflate the error count.
    if os.path.isfile(errors_file):
        with open(errors_file, encoding="utf-8", errors="replace") as fh:
            job.errors = list(dict.fromkeys(
                l.strip() for l in fh if l.strip()
            ))
    # SomeDL has no error file; its end-of-run summary carries the count
    # (last occurrence = most recent retry round).
    if job.tool == "somedl" and os.path.isfile(job.log_path):
        with open(job.log_path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        failed = re.findall(r"Failed downloads:\s+(\d+)", text)
        if failed and int(failed[-1]) > 0:
            job.errors.append(
                f"{failed[-1]} download(s) failed (details: {job.log_path})"
            )


def run_fetch(inputs: list[str], timeout_s: float | None = DOWNLOAD_TIMEOUT,
              retry_rounds: int = 2, quiet: bool = False) -> list[FetchJob]:
    bootstrap()
    missing = [k for k, v in tool_versions().items() if not v]
    if missing:
        raise RuntimeError(
            f"fetch tools missing: {', '.join(missing)} — re-run install.bat"
        )

    pairs: list[tuple[str, str]] = []
    for arg in inputs:
        pairs.extend(classify(arg))
    unsupported = [v for k, v in pairs if k == "unsupported"]
    pairs = [(k, _resolve_shortlink(v) if k == "spotify" else v)
             for k, v in pairs if k != "unsupported"]
    if unsupported:
        for u in unsupported:
            print(f"unsupported source (not Spotify/YouTube): {u}")

    log_dir = os.path.join(reports_dir(), "fetch")
    os.makedirs(log_dir, exist_ok=True)

    jobs: list[FetchJob] = []
    for kind, query in pairs:
        tool = "spotdl" if kind == "spotify" else "somedl"
        job_dir = _new_job_dir(kind, query)
        job = FetchJob(
            job_id=os.path.basename(job_dir),
            kind=kind, tool=tool, query=query,
            job_dir=job_dir,
            log_path=os.path.join(log_dir, f"{os.path.basename(job_dir)}.log"),
        )
        errors_file = os.path.join(log_dir, f"{os.path.basename(job_dir)}.errors")
        print(f"fetch: [{tool}] {query}")
        print(f"  -> {job.job_dir}")

        # Retry rounds: YouTube hiccups (bot checks, throttling) are often
        # transient. Existing files in the job dir are skipped by the tools,
        # so re-running is idempotent. Stop when nothing improved.
        deadline = time.monotonic() + timeout_s if timeout_s else None
        job.returncode = _run_logged(
            _tool_argv(job, errors_file), job.log_path, job, deadline_s=deadline,
        )
        _collect(job, errors_file)
        for round_no in range(1, retry_rounds + 1):
            prev = (len(job.files), len(job.errors), job.returncode)
            if not job.errors and job.returncode == 0:
                break
            print(f"  retry round {round_no} "
                  f"({len(job.errors)} error line(s) so far)")
            with open(job.log_path, "a", encoding="utf-8") as log:
                log.write(f"\n===== retry round {round_no} =====\n")
            job.returncode = _run_logged(
                _tool_argv(job, errors_file), job.log_path, job,
                deadline_s=(time.monotonic() + timeout_s if timeout_s else None),
            )
            _collect(job, errors_file)
            if (len(job.files), len(job.errors), job.returncode) == prev:
                print("  no progress, stopping retries")
                break
        jobs.append(job)
        print(f"  done: {len(job.files)} file(s), {len(job.errors)} error line(s), "
              f"rc={job.returncode}")
    return jobs


def cmd_fetch(inputs: list[str], self_test: bool = False,
              do_import: bool = False) -> int:
    if self_test:
        ok = True
        for name, ver in tool_versions().items():
            print(f"{name}: {ver if ver else 'MISSING'}")
            ok = ok and bool(ver)
        return 0 if ok else 1

    jobs = run_fetch(inputs)
    if not jobs:
        print("fetch: nothing to download (no supported link or search text)")
        return 1
    failed = [j for j in jobs if not j.ok or not j.files]
    print()
    for j in jobs:
        status = "OK" if (j.ok and j.files) else "INCOMPLETE"
        print(f"fetch {status}: {j.query}")
        print(f"  {len(j.files)} track(s) in {j.job_dir}")
        if j.errors:
            print(f"  {len(j.errors)} error line(s): {j.log_path}")
    if do_import:
        for j in jobs:
            if j.files:
                _import_job(j)
            print()
            print(summarize_job(j))
    return 1 if failed else 0


# --------------------------------------------------------------------------
# import chain (fetch --import, and the bot's job worker)
# --------------------------------------------------------------------------

# statuses that mean "a human should look at this eventually"
_OPEN_STATUSES = {"review", "unmatched", "network", "error", "pending"}


def _unit_label(u: dict) -> str:
    """Human label for an imported unit, preferring what the decider chose."""
    seen: list[str] = []
    for r in u.get("file_results") or []:
        c = r.get("chosen") or {}
        g = r.get("guessed") or {}
        artist = c.get("artist") or g.get("artist")
        album = c.get("album") or g.get("album")
        if not artist:
            continue
        if album:
            year = c.get("year")
            seen.append(f"{artist} - {album}" + (f" ({year})" if year else ""))
        else:
            seen.append(f"{artist} - {c.get('track_title') or album}")
    if seen:
        head = seen[0]
        return head if len(seen) == 1 else f"{head} (+{len(seen) - 1})"
    g = u.get("guessed") or {}
    if g.get("artist") or g.get("album"):
        return f"{g.get('artist', '?')} - {g.get('album', '?')}"
    artists = u.get("artists_seen") or []
    return artists[0] if artists else os.path.basename(u.get("path", ""))


def _import_job(job: FetchJob) -> list[tuple[str, str]]:
    """Run the full non-interactive chain for one fetch job's folder.

    scan -> import (decider auto-accepts; ambiguous units land in review)
    -> asis fallback for review/unmatched units with complete tags
    -> cleanup of the emptied staging folder. Returns (status, label)
    for every unit under the job dir.
    """
    from . import asis as asis_mod
    from . import cleanup as cleanup_mod
    from . import engine
    from . import scan as scan_mod
    from . import state as state_mod

    root = os.path.normpath(job.job_dir)
    print(f"import: scanning {root}")
    scan_mod.cmd_scan(root)

    # A link that produced a single track (track links, or an album where
    # all but one download failed) imports as a singleton -> Singles\ path,
    # not as a one-track "album" folder. Scoped to this job's units only.
    st = state_mod.load()
    units = state_mod.units(st)
    root_key = os.path.normcase(root)
    patched = 0
    for key, u in units.items():
        k = os.path.normcase(os.path.normpath(key))
        if k != root_key and not k.startswith(root_key + os.sep):
            continue
        if u.get("n_files", 0) == 1 and not u.get("singleton"):
            u["singleton"] = True
            u["split_into_singletons"] = False
            patched += 1
    if patched:
        state_mod.save(st)
        print(f"import: {patched} single-track unit(s) import as singletons")

    print("import: running import (musicbrainz chain)")
    engine.cmd_import(only=root)
    print("import: asis fallback for review/unmatched units")
    asis_mod.cmd_asis(only=root)
    # beets already removes emptied source dirs after the move; cleanup
    # only has work left when files remained (corrupt leftovers, .nfo junk).
    if os.path.isdir(root):
        cleanup_mod.cmd_cleanup(root=root)

    st = state_mod.load()
    outcomes = []
    root_key = os.path.normcase(root)
    albums: list[tuple[str, str]] = []
    for key, u in sorted(state_mod.units(st).items()):
        k = os.path.normcase(os.path.normpath(key))
        if k != root_key and not k.startswith(root_key + os.sep):
            continue
        outcomes.append((u.get("status", "?"), _unit_label(u)))
        if u.get("status") in ("auto", "asis") and not u.get("singleton"):
            # as-is units carry identity in `guessed`/`candidates` (chosen
            # is null); auto album units in file_results->chosen.
            c = (u.get("chosen")
                 or ((u.get("file_results") or [{}])[0].get("chosen"))
                 or (u.get("candidates") or [{}])[0]
                 or {})
            g = u.get("guessed") or {}
            artist = c.get("artist") or g.get("artist")
            album = c.get("album") or g.get("album")
            if album:
                albums.append((artist or "", album))

    # As-is imports skip the autotag pipeline's art/genre stages; the files
    # carry embedded covers from the downloaders, but the album row still
    # wants genres and a cover file. Both backfills only fill gaps.
    if albums:
        print("import: enriching art/genre for imported albums")
        _enrich_albums(albums)

    counts: dict[str, int] = {}
    for status, _ in outcomes:
        counts[status] = counts.get(status, 0) + 1
    print("import outcome:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    for status, label in outcomes:
        print(f"  [{status}] {label}")
    job.outcomes = outcomes
    return outcomes


def _enrich_albums(albums: list[tuple[str, str]]) -> None:
    """Targeted lastgenre + fetchart backfill for freshly imported albums."""
    # bootstrap() (not yet run when called standalone) puts bin/ with
    # ffmpeg on PATH; without it replaygain dies at plugin init and beets
    # swallows the error (2.13 plugin behavior) without running anything.
    bootstrap()
    env = dict(os.environ)

    for artist, album in dict.fromkeys(albums):
        # NOTE: beets treats quotes inside a query value literally
        # (albumartist:"X" matches nothing) — pass values unquoted, one
        # argv element each.
        query = [f"album:{album}"]
        if artist:
            query.insert(0, f"albumartist:{artist}")
        for what in ("lastgenre", "fetchart"):
            try:
                r = subprocess.run(
                    [sys.executable, "-m", "beets", what, *query],
                    env=env, capture_output=True, text=True,
                    errors="replace", timeout=600,
                )
            except subprocess.TimeoutExpired:
                print(f"  {what} backfill timed out for {artist} - {album}")
                continue
            if r.returncode != 0:
                err = (r.stderr or r.stdout or "").strip()[:120]
                print(f"  {what} backfill failed for {artist} - {album}: {err}")


def summarize_job(job: "FetchJob") -> str:
    """One-paragraph result summary (bot messages, session reports)."""
    lines = [f"{job.query}"]
    lines.append(f"{len(job.files)} Track(s) heruntergeladen")
    failed = len(job.errors)
    if failed:
        lines.append(f"{failed} Fehler/fehlgeschlagene Track(s) — Log: {job.log_path}")
    if job.timed_out:
        lines.append("Zeitlimit erreicht, Job wurde abgebrochen")
    for status, label in job.outcomes:
        note = {
            "auto": "importiert (MusicBrainz-Match)",
            "asis": "importiert (eigene Tags)",
            "duplicate": "Duplikat — bessere Kopie existierte schon",
        }.get(status, f"Status {status} — liegt weiter in _incoming")
        lines.append(f"• {label}: {note}")
    if not job.outcomes:
        lines.append("kein Import (nichts Klassifizierbares heruntergeladen)")
    return "\n".join(lines)
