from __future__ import annotations

import argparse
import asyncio
import json

from . import __version__
from .server import DEFAULT_HOST, DEFAULT_PORT, EngineServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="XAUPY Python Engine IPC server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser


async def run_server(host: str, port: int) -> int:
    server = EngineServer(host=host, port=port)
    await server.start()

    print(
        json.dumps(
            {
                "event": "engine_ready",
                "version": __version__,
                "host": server.host,
                "port": server.bound_port,
                "trading_enabled": False,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )

    try:
        await server.wait_for_shutdown()
    finally:
        await server.close()

    return 0


def main() -> int:
    args = build_parser().parse_args()

    try:
        return asyncio.run(run_server(args.host, args.port))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
