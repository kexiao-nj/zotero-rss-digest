from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import load_app_config
from .pipeline import probe, run_pipeline

log = logging.getLogger("zotero_rss")


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _print_probe(result) -> int:
    print(f"Data dir:     {result.data_dir}")
    print(f"Local API:    {'OK' if result.local_api_ok else 'FAIL'} — {result.local_api_detail}")
    print(f"Feeds HTTP:   {'yes' if result.feeds_http_ok else 'no (SQLite fallback)'}")
    print(f"SQLite:       {'OK' if result.sqlite_ok else 'FAIL'} — {result.sqlite_detail}")
    if result.feeds:
        print()
        print(f"{'Feed':<55} {'items':>6} {'unread':>6}  last check")
        for feed in result.feeds:
            err = f"  ERR:{feed.last_check_error}" if feed.last_check_error else ""
            print(
                f"{feed.name[:55]:<55} {feed.item_count:>6} {feed.unread_count:>6}  "
                f"{feed.last_check or '—'}{err}"
            )
        print()
        print(f"Total RSS items: {result.total_items} (unread {result.unread_items})")
    return 0 if result.sqlite_ok else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zotero-rss",
        description="Read Zotero RSS feeds and write a periodic digest.",
    )
    parser.add_argument(
        "-c",
        "--config-dir",
        type=Path,
        default=None,
        help="Directory containing config.yaml and research_profile.yaml",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("probe", help="Check Local API and list RSS feeds")

    run = sub.add_parser("run", help="Ingest new RSS items and write today's digest")
    run.add_argument("--no-llm", action="store_true", help="Skip LLM scoring/cards")
    run.add_argument("--no-enrich", action="store_true", help="Skip Crossref/OpenAlex/arXiv")
    run.add_argument(
        "--all",
        action="store_true",
        dest="process_all",
        help="Process every current feed item, not only unseen GUIDs",
    )
    run.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="On first run, only treat items from the last N days as new",
    )

    since = sub.add_parser(
        "digest-since",
        help="Re-digest feed items on or after YYYY-MM-DD (still marks GUIDs seen)",
    )
    since.add_argument("date", help="ISO date, e.g. 2026-09-01")
    since.add_argument("--no-llm", action="store_true")
    since.add_argument("--no-enrich", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    cfg = load_app_config(args.config_dir)
    if args.command == "probe":
        return _print_probe(probe(cfg))
    if args.command == "run":
        stats = run_pipeline(
            cfg,
            use_llm=not args.no_llm,
            enrich=not args.no_enrich,
            lookback_days=args.lookback_days,
            process_all=args.process_all,
        )
        print(stats.message)
        return 0
    if args.command == "digest-since":
        stats = run_pipeline(
            cfg,
            use_llm=not args.no_llm,
            enrich=not args.no_enrich,
            since=args.date,
        )
        print(stats.message)
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
