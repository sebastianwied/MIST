#!/usr/bin/env python3
"""Standalone echo-agent demo.

Starts a Unix-socket server that echoes every command back as a
response, connects a client, sends three messages, and prints the
replies.

Usage:
    python core/examples/echo_agent.py
"""

import asyncio
import sys
from pathlib import Path

# Allow running from the repo root without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mist_core.protocol import Message, MSG_COMMAND, MSG_RESPONSE
from mist_core.transport import Client, Connection, Server

SOCKET = Path("/tmp/mist-echo-test.sock")


async def echo_handler(msg: Message, conn: Connection) -> None:
    reply = Message.reply(msg, sender="echo-server", type=MSG_RESPONSE, payload=msg.payload)
    await conn.send(reply)


async def main() -> None:
    server = Server(echo_handler, path=SOCKET)
    await server.start()
    print(f"Server listening on {SOCKET}")

    client = Client(path=SOCKET)
    await client.connect()
    print("Client connected\n")

    try:
        for i in range(3):
            msg = Message.create(
                MSG_COMMAND,
                sender="demo-client",
                to="echo-server",
                payload={"seq": i, "text": f"hello {i}"},
            )
            print(f"  -> send: {msg.payload}")
            reply = await client.request(msg, timeout=2.0)
            print(f"  <- recv: {reply.payload}")
        print("\nDone.")
    finally:
        client.close()
        await client.wait_closed()
        await server.stop()
        print("Cleaned up.")


if __name__ == "__main__":
    asyncio.run(main())
