"""Entry point for the mist-broker command."""

from __future__ import annotations

import argparse
import asyncio
import logging

from mist_core.transport import DEFAULT_SOCKET_PATH

from .broker import Broker


def main() -> None:
    parser = argparse.ArgumentParser(description="MIST message broker")
    parser.add_argument(
        "--socket-path",
        default=str(DEFAULT_SOCKET_PATH),
        help=f"Unix socket path (default: {DEFAULT_SOCKET_PATH})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    broker = Broker(socket_path=args.socket_path)
    asyncio.run(broker.run())


if __name__ == "__main__":
    main()
