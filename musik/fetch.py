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

from .paths import bootstrap, incoming_dir, reports_dir, state_dir

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


def _tool_argv(job: FetchJob, errors_file: str, archive_file: str) -> list[str]:
    if job.kind == "spotify":
        return [
            *spotdl_cmd(), "download", job.query,
            "--output", os.path.join(job.job_dir, "{artists} - {title}.{output-ext}"),
            "--format", "m4a",
            "--print-errors", "--save-errors", errors_file,
            "--archive", archive_file,
            "--threads", "4",
        ]
    # youtube link or free-text search -> SomeDL (flat default template)
    return [
        *somedl_cmd(), job.query,
        "-o", job.job_dir,
        "-f", "best/m4a",
        "--disable-report",
        "--download-archive", archive_file,
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
    if os.path.isfile(errors_file):
        with open(errors_file, encoding="utf-8", errors="replace") as fh:
            job.errors.extend(
                l.strip() for l in fh if l.strip()
            )
    # SomeDL has no error file; its end-of-run summary carries the count.
    if job.tool == "somedl" and os.path.isfile(job.log_path):
        with open(job.log_path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        m = re.search(r"Failed downloads:\s+(\d+)", text)
        if m and int(m.group(1)) > 0:
            job.errors.append(
                f"{m.group(1)} download(s) failed (details: {job.log_path})"
            )


def run_fetch(inputs: list[str], timeout_s: float | None = DOWNLOAD_TIMEOUT,
              quiet: bool = False) -> list[FetchJob]:
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
    os.makedirs(state_dir(), exist_ok=True)

    jobs: list[FetchJob] = []
    for i, (kind, query) in enumerate(pairs):
        tool = "spotdl" if kind == "spotify" else "somedl"
        job_dir = _new_job_dir(kind, query)
        job = FetchJob(
            job_id=os.path.basename(job_dir),
            kind=kind, tool=tool, query=query,
            job_dir=job_dir,
            log_path=os.path.join(log_dir, f"{os.path.basename(job_dir)}.log"),
        )
        errors_file = os.path.join(log_dir, f"{os.path.basename(job_dir)}.errors")
        archive_file = os.path.join(state_dir(), f"fetch-archive-{tool}.txt")
        print(f"fetch: [{tool}] {query}")
        print(f"  -> {job.job_dir}")
        job.returncode = _run_logged(
            _tool_argv(job, errors_file, archive_file),
            job.log_path, job, deadline_s=(time.monotonic() + timeout_s
                                           if timeout_s else None),
        )
        _collect(job, errors_file)
        jobs.append(job)
        print(f"  done: {len(job.files)} file(s), {len(job.errors)} error line(s), "
              f"rc={job.returncode}")
    return jobs


def cmd_fetch(inputs: list[str], self_test: bool = False) -> int:
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
    return 1 if failed else 0
