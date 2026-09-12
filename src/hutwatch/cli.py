from __future__ import annotations

import argparse
import logging
import sys

from hutwatch.config import load_config
from hutwatch.fetchers import build_fetcher
from hutwatch.monitor import run_dry_run, run_once
from hutwatch.notifiers import build_notifiers
from hutwatch.poller import run_forever
from hutwatch.providers import load_provider
from hutwatch.robots import RobotsDisallowedError, check_allowed
from hutwatch.state import StateStore
from hutwatch.status_page import render_status_html


def _build_user_agent(contact_email: str) -> str:
    return f"hutwatch/0.1 (+read-only availability monitor; contact: {contact_email})"


def _print_status(config, limit: int = 1) -> None:
    state = StateStore(config.state.db_path)
    try:
        for target in config.targets:
            print(f"=== {target.label} ===")
            records = state.recent_checks(limit=limit, label=target.label)
            if not records:
                print("No checks logged yet.")
            else:
                for record in records:
                    print(f"timestamp:    {record.timestamp}")
                    print(f"beds:         {record.beds if record.beds is not None else 'unknown'}")
                    print(f"room_type:    {record.room_type or '-'}")
                    print(f"http_status:  {record.http_status if record.http_status is not None else '-'}")
                    print(f"error:        {record.error or '-'}")
                    print("-")
            print(f"consecutive_failures: {state.get_consecutive_failures(target.label)}")
            print(f"alert_armed:          {state.is_armed(target.label)}")
            print()
    finally:
        state.close()


def _render_status_page(config, output_path: str, limit: int = 20) -> None:
    state = StateStore(config.state.db_path)
    try:
        html_text = render_status_html(config, state, limit=limit)
    finally:
        state.close()
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hutwatch", description="Mountain hut availability monitor")
    parser.add_argument("--config", default="config.toml", help="Path to config.toml")
    parser.add_argument("--once", action="store_true", help="Run a single check and exit")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Send a fake positive-availability notification to test the alert path, then exit",
    )
    parser.add_argument(
        "--status",
        nargs="?",
        const=1,
        type=int,
        default=None,
        metavar="N",
        help="Print the N most recent logged checks (default 1) from the state database and exit",
    )
    parser.add_argument(
        "--render-status",
        metavar="PATH",
        default=None,
        help="Write a static HTML status page to PATH (from the state database) and exit",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config(args.config)

    if args.status is not None:
        _print_status(config, limit=args.status)
        return 0

    if args.render_status is not None:
        _render_status_page(config, args.render_status)
        return 0

    user_agent = _build_user_agent(config.fetch.contact_email)

    try:
        check_allowed(config.hut.url, user_agent)
    except RobotsDisallowedError as exc:
        logging.getLogger(__name__).error("Refusing to run: %s", exc)
        return 1

    notifiers = build_notifiers(config.notifiers)

    if args.dry_run:
        run_dry_run(config, notifiers)
        return 0

    provider = load_provider(config.hut.provider)
    fetcher = build_fetcher(config.fetch)
    state = StateStore(config.state.db_path)

    try:
        if args.once:
            run_once(config, fetcher, provider, state, notifiers)
        else:
            run_forever(config, fetcher, provider, state, notifiers)
    finally:
        fetcher.close()
        state.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
