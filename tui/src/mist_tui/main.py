"""Entry point for mist-tui."""

from __future__ import annotations

import argparse
import logging

from .app import MistApp


def main() -> None:
    parser = argparse.ArgumentParser(description="MIST TUI")
    parser.add_argument(
        "--socket-path",
        default=None,
        help="Path to broker Unix socket (default: data/broker/mist.sock)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Launch in demo mode (no broker needed)",
    )
    parser.add_argument(
        "--no-managed",
        action="store_true",
        help="Skip launcher screen (don't manage broker/agent processes)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if args.demo:
        from .demo import DemoApp
        DemoApp().run()
    else:
        MistApp(
            socket_path=args.socket_path,
            managed=not args.no_managed,
        ).run()


if __name__ == "__main__":
    main()
