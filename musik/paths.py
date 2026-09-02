"""Project layout and beets bootstrap.

Sets BEETSDIR so beets picks up this project's config.yaml (and finds
discogs_token.json next to it), and points pyacoustid at the bundled
fpcalc.exe. Must run before `import beets` anywhere in the process.
"""

import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.yaml")
DISCOGS_TOKEN_FILE = os.path.join(PROJECT_DIR, "discogs_token.json")
BIN_DIR = os.path.join(PROJECT_DIR, "bin")
FPCALC = os.path.join(BIN_DIR, "fpcalc.exe")

DEFAULT_STATE_DIR = os.path.join(PROJECT_DIR, "state")
DEFAULT_REPORTS_DIR = os.path.join(PROJECT_DIR, "reports")

_bootstrapped = False


def bootstrap() -> None:
    global _bootstrapped
    if _bootstrapped:
        return
    _bootstrapped = True

    # Force this project's beets config; the tool owns the beets setup.
    os.environ["BEETSDIR"] = PROJECT_DIR
    if os.path.isfile(FPCALC):
        os.environ["FPCALC"] = FPCALC


def _musik_config() -> dict:
    """Read the `musik:` section of config.yaml (plain yaml, no beets)."""
    import yaml

    with open(CONFIG_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("musik") or {}


def musik_config() -> dict:
    cfg = _musik_config()
    cfg.setdefault(
        "trash_dir", os.path.join(cfg_dir_default_trash(), "_trash")
    )
    cfg.setdefault("state_dir", DEFAULT_STATE_DIR)
    cfg.setdefault("reports_dir", DEFAULT_REPORTS_DIR)
    cfg.setdefault("auto_accept_distance", 0.08)
    cfg.setdefault("review_candidates", 3)
    cfg.setdefault("retry_rounds", 2)
    cfg.setdefault("retry_cooldown_seconds", 20)
    return cfg


def cfg_dir_default_trash() -> str:
    home = os.path.expanduser("~")
    return os.path.join(home, "Music")


def state_dir() -> str:
    return musik_config()["state_dir"]


def reports_dir() -> str:
    d = musik_config()["reports_dir"]
    os.makedirs(d, exist_ok=True)
    return d


def trash_dir() -> str:
    d = musik_config()["trash_dir"]
    os.makedirs(d, exist_ok=True)
    return d
