"""Remote-download toolchain (`musik fetch`).

Bridges Spotify links to spotDL and YouTube/YT-Music links (or free-text
searches) to SomeDL, both driven as pinned CLI subprocesses (see
requirements.txt — spotDL's Python API is unstable, SomeDL documents none).
Downloads land in a staging folder under the library root and are then run
through the normal scan/import pipeline.

This part: tool discovery + version checks (used by `musik doctor`).
"""

import os
import shutil
import subprocess
import sys
import sysconfig

from .paths import bootstrap

VERSION_TIMEOUT = 60


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
