# -*- coding: utf-8 -*-
"""Run the whole smoke suite (manual_tests/smoke_*.py) as subprocesses.

Run:  python manual_tests/run_smokes.py [name-filter ...]
Story 6.6: ein Einstiegspunkt für CI und für den Pi-Nachlauf — jede
Smoke-Datei läuft isoliert (eigener Interpreter, utf-8 erzwingen),
Output erscheint nur bei Fehlern komplett. Exit 1, wenn ein Smoke fails.

Die Suite ist bewusst netzfrei und beets-arm: die Smokes mocken
Kollaboratoren; ein Rechner ohne Bibliothek/Netz kann sie alle laufen
lassen (die CI führt sie nach jedem install.sh aus).
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main(argv: list[str]) -> int:
    filters = [a.lower() for a in argv]
    smokes = sorted(
        f for f in os.listdir(HERE)
        if f.startswith("smoke_") and f.endswith(".py")
        and all(x in f.lower() for x in filters)
    )
    if not smokes:
        print("no smoke files matched:", filters or "(all)")
        return 2

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    failed: list[str] = []
    timings: list[tuple[str, float]] = []
    for name in smokes:
        start = time.monotonic()
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, name)],
            cwd=ROOT, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        dur = time.monotonic() - start
        timings.append((name, dur))
        if proc.returncode != 0:
            failed.append(name)
            print(f"FAIL  {name}  ({dur:.1f}s)")
            out = (proc.stdout or "") + (proc.stderr or "")
            tail = out.strip().splitlines()[-30:]
            for line in tail:
                print("      " + line)
        else:
            print(f"pass  {name}  ({dur:.1f}s)")

    print("-" * 60)
    print(f"{len(smokes) - len(failed)}/{len(smokes)} smoke file(s) passed"
          f" in {sum(d for _, d in timings):.1f}s")
    if failed:
        print("failed:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
