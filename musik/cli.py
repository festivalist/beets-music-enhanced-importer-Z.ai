"""musik command line interface."""

import argparse
import os
import sys


def _default_scan_root() -> str:
    import yaml

    from .paths import CONFIG_FILE, PROJECT_DIR

    try:
        with open(CONFIG_FILE, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        directory = data.get("directory") or os.path.join(
            os.path.expanduser("~"), "Music"
        )
    except Exception:
        directory = os.path.join(os.path.expanduser("~"), "Music")
    unsorted_ = os.path.join(directory, "unsorted")
    return unsorted_ if os.path.isdir(unsorted_) else directory


def main(argv: list[str] | None = None) -> int:
    # Windows consoles may not be UTF-8; never crash on path printing.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="musik",
        description="Automated MusicBrainz tagging for a large music library.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_setup = sub.add_parser(
        "setup", help="first-run wizard: generate config.yaml for this machine"
    )
    p_setup.add_argument("--library", default=None,
                         help="music library root (default: %%USERPROFILE%%\\Music)")
    p_setup.add_argument("--discogs-token", default=None,
                         help="Discogs personal access token (empty = skip)")
    p_setup.add_argument("--unsorted", default=None,
                         help="optional: your incoming-music folder (shown in next steps)")

    p_scan = sub.add_parser("scan", help="classify the library into import units (read-only)")
    p_scan.add_argument("--root", default=_default_scan_root())

    p_imp = sub.add_parser("import", help="import units (dry-run first!)")
    p_imp.add_argument("--dry-run", action="store_true",
                       help="lookups and decisions only; nothing moves")
    p_imp.add_argument("--limit", type=int, default=None, help="process at most N units")
    p_imp.add_argument("--unit", default=None, help="process exactly this unit path")
    p_imp.add_argument("--status", action="append", default=None,
                       help="unit statuses to process (repeatable; default: pending)")
    p_imp.add_argument("--rounds", type=int, default=None,
                       help="retry rounds for network-deferred units")
    p_imp.add_argument("--quiet", action="store_true")

    p_ret = sub.add_parser("retry", help="retry network-deferred (and optionally unmatched) units")
    p_ret.add_argument("--include-unmatched", action="store_true")
    p_ret.add_argument("--rounds", type=int, default=None)

    p_app = sub.add_parser("apply", help="process decisions from review.csv")
    p_app.add_argument("--csv", default=None)

    p_rev = sub.add_parser(
        "review",
        help="interactive decisions for review units (accept/override/asis/skip/abort)",
    )
    p_rev.add_argument("--unit", default=None, help="folder prefix or exact unit path")

    p_rep = sub.add_parser("report", help="write reports; --verify checks the library DB")
    p_rep.add_argument("--verify", action="store_true")

    p_ded = sub.add_parser("dedupe", help="resolve duplicates in the library by quality")
    p_ded.add_argument("--dry-run", action="store_true")

    p_asis = sub.add_parser(
        "asis",
        help="file review/unmatched units with complete tags using their own tags (explicit opt-in)",
    )
    p_asis.add_argument("--unit", default=None, help="folder prefix or exact unit path")
    p_asis.add_argument("--dry-run", action="store_true", help="list eligible units only")

    args = parser.parse_args(argv)

    if args.cmd != "setup" and not os.path.isfile(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "config.yaml")
    ):
        print("no config.yaml found — run the setup wizard first:")
        print("  python musik.py setup")
        return 1

    if args.cmd == "setup":
        from . import setup

        return setup.cmd_setup(
            library=args.library,
            discogs_token=args.discogs_token,
            unsorted=args.unsorted,
        )

    if args.cmd == "scan":
        from . import scan

        return scan.cmd_scan(args.root)

    if args.cmd == "import":
        from . import engine

        return engine.cmd_import(
            dry_run=args.dry_run,
            statuses=args.status,
            limit=args.limit,
            only=args.unit,
            rounds=args.rounds,
            quiet=args.quiet,
        )

    if args.cmd == "retry":
        from . import engine

        return engine.cmd_retry(
            rounds=args.rounds, include_unmatched=args.include_unmatched
        )

    if args.cmd == "apply":
        from . import review

        return review.apply_decisions(args.csv)

    if args.cmd == "review":
        from . import interactive

        return interactive.cmd_review(args.unit)

    if args.cmd == "report":
        from . import state as state_mod
        from . import report as report_mod

        st = state_mod.load()
        path = report_mod.write_import_report(st)
        print("report:", path)
        if args.verify:
            v = report_mod.verify(st)
            print("verification:", v)
        return 0

    if args.cmd == "dedupe":
        from . import dedupe

        return dedupe.cmd_dedupe(dry_run=args.dry_run)

    if args.cmd == "asis":
        from . import asis

        return asis.cmd_asis(only=args.unit, dry_run=args.dry_run)

    parser.error(f"unknown command {args.cmd}")
