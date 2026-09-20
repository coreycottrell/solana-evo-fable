"""CLI for fable paper colony."""

from __future__ import annotations

import argparse
import logging
import os
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="evobot", description="Evo-Bot Fable v2 paper colony")
    p.add_argument("--paper", action="store_true", help="run paper evolution loop")
    p.add_argument("--cadence", type=float, default=14400.0, help="cadence seconds")
    p.add_argument("--poll", type=float, default=90.0, help="poll seconds")
    p.add_argument("--organisms", type=int, default=8)
    p.add_argument("--dashboard", action="store_true")
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--once", action="store_true", help="single poll then exit")
    p.add_argument(
        "--jev-once",
        action="store_true",
        help="one market-only Jev Decisions call on current tape, then exit",
    )
    p.add_argument(
        "--jev-mock",
        action="store_true",
        help="force mock Jev (sets EVO_BOT_JEV_MOCK=1)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    os.environ.setdefault("EVO_BOT_V2_DATA_DIR", os.environ.get("EVO_BOT_V2_DATA_DIR") or "data")

    if args.jev_mock:
        os.environ["EVO_BOT_JEV_MOCK"] = "1"
    else:
        # Turn OFF default mock when OPENROUTER_API_KEY is available.
        from evobot.jev_client import resolve_api_key

        if "EVO_BOT_JEV_MOCK" not in os.environ:
            if resolve_api_key():
                os.environ["EVO_BOT_JEV_MOCK"] = "0"
            else:
                os.environ["EVO_BOT_JEV_MOCK"] = "1"

    if args.jev_once:
        from evobot.live.runner import run_jev_once_cli

        return run_jev_once_cli()

    if not args.paper:
        p.print_help()
        return 2

    from evobot.live.runner import run_paper

    run_paper(
        cadence_sec=args.cadence,
        poll_sec=args.poll,
        n_organisms=args.organisms,
        dashboard_port=args.port if args.dashboard else None,
        once=args.once,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
