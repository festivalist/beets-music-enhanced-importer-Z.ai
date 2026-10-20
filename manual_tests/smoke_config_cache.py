# -*- coding: utf-8 -*-
"""Regression test for the config cache (Story 9.7 hotfix, 2026-10-20).

Run:  python manual_tests/smoke_config_cache.py
Bug: paths.musik_config()/library_root() re-parsed config.yaml on EVERY
call; the Monitor snapshot does that hundreds of times per request and
drove the bot's HTTP threads into CPU saturation (endpoint timeouts,
empty Monitor tab). Pins: one yaml parse for many calls, an mtime bump
triggers exactly one re-parse, and musik_config() returns a copy (caller
mutations must not leak into the cache).
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import musik.paths as paths_mod  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = os.path.join(tmp, "config.yaml")
        with open(cfg_path, "w", encoding="utf-8") as fh:
            fh.write("musik:\n  bot_allowlist: [1]\ndirectory: /lib\n")
        paths_mod.CONFIG_FILE = cfg_path

        import yaml

        real_load = yaml.safe_load
        calls = {"n": 0}

        def counting_load(fh, *a, **k):
            calls["n"] += 1
            return real_load(fh, *a, **k)

        yaml.safe_load = counting_load
        try:
            # 1) viele Aufrufe → genau EIN Parse
            paths_mod.musik_config()
            paths_mod.musik_config()
            paths_mod.musik_config()
            assert paths_mod.library_root() == "/lib"
            assert calls["n"] == 1, calls

            # 2) Kopie-Semantik: Mutationen des Rückgabewerts bleiben draußen
            cfg = paths_mod.musik_config()
            cfg["bot_allowlist"] = [999]
            cfg["state_dir"] = "/gemutated"
            assert paths_mod.musik_config()["state_dir"] == \
                paths_mod.DEFAULT_STATE_DIR
            assert paths_mod.musik_config()["bot_allowlist"] == [1]
            assert calls["n"] == 1, calls

            # 3) mtime-Bump → genau ein Re-Parse, neuer Wert sichtbar
            future = os.path.getmtime(cfg_path) + 10
            os.utime(cfg_path, (future, future))
            with open(cfg_path, "w", encoding="utf-8") as fh:
                fh.write("musik:\n  bot_allowlist: [2]\ndirectory: /lib2\n")
            os.utime(cfg_path, (future + 5, future + 5))
            assert paths_mod.musik_config()["bot_allowlist"] == [2]
            assert paths_mod.library_root() == "/lib2"
            assert calls["n"] == 2, calls
        finally:
            yaml.safe_load = real_load

    print("smoke_config_cache: alle Assertionen grün")
    return 0


if __name__ == "__main__":
    sys.exit(main())
