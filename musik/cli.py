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
    p_imp.add_argument("--exclude", action="append", default=None,
                       help="skip units at or under this folder prefix (repeatable)")
    p_imp.add_argument("--sources", default=None,
                       help="comma-separated metadata sources to enable "
                            "(e.g. musicbrainz,beatport4; default: all configured)")
    p_imp.add_argument("--status", action="append", default=None,
                       help="unit statuses to process (repeatable; default: pending)")
    p_imp.add_argument("--rounds", type=int, default=None,
                       help="retry rounds for network-deferred units")
    p_imp.add_argument("--quiet", action="store_true")

    p_ret = sub.add_parser("retry", help="retry network-deferred (and optionally unmatched) units")
    p_ret.add_argument("--include-unmatched", action="store_true")
    p_ret.add_argument("--rounds", type=int, default=None)
    p_ret.add_argument("--sources", default=None,
                       help="comma-separated metadata sources (see import --sources)")

    p_app = sub.add_parser("apply", help="process decisions from review.csv")
    p_app.add_argument("--csv", default=None)

    p_rev = sub.add_parser(
        "review",
        help="interactive decisions for review units (accept/override/asis/skip/abort)",
    )
    p_rev.add_argument("--unit", default=None, help="folder prefix or exact unit path")

    p_rep = sub.add_parser("report", help="write reports; --verify checks the library DB")
    p_rep.add_argument("--fix", action="store_true",
                       help="with --verify: remove DB rows whose files are gone")
    p_rep.add_argument("--verify", action="store_true")

    sub.add_parser("session-begin",
                   help="mark the start of an import session (import-here.bat does this)")
    sub.add_parser("summary",
                   help="totals of everything decided since the session started")

    p_ded = sub.add_parser("dedupe", help="resolve duplicates in the library by quality")
    p_ded.add_argument("--dry-run", action="store_true")
    p_ded.add_argument("--fingerprint", action="store_true",
                       help="track-level dupe hunt via AcoustID "
                            "(same recording under different metadata; report only)")
    p_ded.add_argument("--apply", action="store_true",
                       help="with --fingerprint: actually trash the lower-quality copies")

    p_clean = sub.add_parser(
        "cleanup",
        help="archive leftovers (.nfo/.sfv/...) of imported albums, remove emptied source folders",
    )
    p_clean.add_argument("--root", required=True, help="source folder to tidy")
    p_clean.add_argument("--dry-run", action="store_true", help="show what would happen")
    p_clean.add_argument("--trash-base", default=None, help=argparse.SUPPRESS)

    p_asis = sub.add_parser(
        "asis",
        help="file review/unmatched units with complete tags using their own tags (explicit opt-in)",
    )
    p_asis.add_argument("--unit", default=None, help="folder prefix or exact unit path")
    p_asis.add_argument("--pending", action="store_true",
                        help="also include pending units (aggressive as-is, no lookup)")
    p_asis.add_argument("--dry-run", action="store_true", help="list eligible units only")

    p_snap = sub.add_parser(
        "snapshot",
        help="zip up beets DB, config, run state and tokens (rotating backup)",
    )
    p_snap.add_argument("--list", action="store_true", help="list existing snapshots")
    p_snap.add_argument("--keep", type=int, default=None,
                        help="keep this many snapshots (default from config)")

    p_doc = sub.add_parser(
        "doctor",
        help="library health check: dead rows, orphans, bitrot, art/genre (report-only by default)",
    )
    p_doc.add_argument("--fix", action="store_true",
                       help="remove dead DB rows, backfill missing art/genre")
    p_doc.add_argument("--quick", action="store_true",
                       help="skip files already decode-tested (mtime/size cache)")
    p_doc.add_argument("--limit", type=int, default=None,
                       help="decode-test at most N files spread across the library (spot check)")

    sub.add_parser("stats", help="library statistics (totals, formats, decades, top artists)")

    p_sim = sub.add_parser(
        "similar",
        help="similar-artist suggestions from ListenBrainz for artists you don't have yet",
    )
    p_sim.add_argument("--top", type=int, default=30, help="size of the top list (default 30)")
    p_sim.add_argument("--refresh", action="store_true",
                       help="re-query all artists, ignoring the cache")

    p_rel = sub.add_parser(
        "releases",
        help="new releases of your library artists since the last run (MusicBrainz)",
    )
    p_rel.add_argument("--since", default=None,
                       help="override lookback start (YYYY-MM-DD; default: last run or 90 days)")

    p_ret2 = sub.add_parser(
        "retag",
        help="re-check as-is-imported albums against MusicBrainz (report only)",
    )
    p_ret2.add_argument("--limit", type=int, default=None, help="only check N albums")
    p_ret2.add_argument("--max-distance", type=float, default=0.10,
                        help="distance under which a match counts as strong (default 0.10)")

    p_fetch = sub.add_parser(
        "fetch",
        help="download a Spotify link (spotDL) or YouTube/YT-Music link / "
             "free-text search (SomeDL) into <library>/_incoming/",
    )
    p_fetch.add_argument("inputs", nargs="*",
                         help="Spotify/YouTube URL(s) or 'artist - title' search text")
    p_fetch.add_argument("--self-test", action="store_true",
                         help="verify spotdl/somedl/ffmpeg are installed and exit")
    p_fetch.add_argument("--import", dest="do_import", action="store_true",
                         help="after downloading: scan + import + asis fallback + "
                              "cleanup (full unattended chain)")

    sub.add_parser(
        "bot",
        help="run the Telegram bot service (link in -> music in the library)",
    )

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
            excludes=args.exclude,
            sources=(args.sources.split(",") if args.sources else None),
            rounds=args.rounds,
            quiet=args.quiet,
        )

    if args.cmd == "retry":
        from . import engine

        return engine.cmd_retry(
            rounds=args.rounds, include_unmatched=args.include_unmatched,
            sources=(args.sources.split(",") if args.sources else None),
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
            v = report_mod.verify(st, fix=args.fix)
            print("verification:", v)
        return 0

    if args.cmd == "session-begin":
        from . import report as report_mod

        return report_mod.cmd_session_begin()

    if args.cmd == "summary":
        from . import report as report_mod

        return report_mod.cmd_summary()

    if args.cmd == "dedupe":
        from . import dedupe

        return dedupe.cmd_dedupe(
            dry_run=args.dry_run, fingerprint=args.fingerprint, apply=args.apply
        )

    if args.cmd == "asis":
        from . import asis

        return asis.cmd_asis(
            only=args.unit, dry_run=args.dry_run, include_pending=args.pending
        )

    if args.cmd == "cleanup":
        from . import cleanup

        return cleanup.cmd_cleanup(
            root=args.root, dry_run=args.dry_run, trash_base=args.trash_base
        )

    if args.cmd == "snapshot":
        from . import backup

        return backup.cmd_snapshot(list_only=args.list, keep=args.keep)

    if args.cmd == "doctor":
        from . import doctor

        return doctor.cmd_doctor(fix=args.fix, quick=args.quick, limit=args.limit)

    if args.cmd == "stats":
        from . import stats

        return stats.cmd_stats()

    if args.cmd == "similar":
        from . import similar

        return similar.cmd_similar(top=args.top, refresh=args.refresh)

    if args.cmd == "releases":
        from . import releases

        return releases.cmd_releases(since=args.since)

    if args.cmd == "retag":
        from . import retag

        return retag.cmd_retag(limit=args.limit, max_distance=args.max_distance)

    if args.cmd == "fetch":
        from . import fetch

        return fetch.cmd_fetch(
            inputs=args.inputs, self_test=args.self_test,
            do_import=args.do_import,
        )

    if args.cmd == "bot":
        from . import bot

        return bot.cmd_bot()

    parser.error(f"unknown command {args.cmd}")
