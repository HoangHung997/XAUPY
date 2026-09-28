from __future__ import annotations

import argparse
import asyncio
import json
import sys

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
    if len(sys.argv) > 1 and sys.argv[1] == '--collect-ticks':
        from .tick_collect import main as collect_ticks
        collect_ticks(sys.argv[2:])
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "--collect-broker-history":
        from pathlib import Path
        from .broker_history import collect
        path = Path(sys.argv[2])
        request = json.loads(path.read_text(encoding='utf-8'))
        collect(request['terminal'], path.parent, request['identity'])
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "--history-provider-check":
        # MetaTrader5's native extension imports NumPy dynamically. Keep this
        # explicit so frozen builds include its runtime and native libraries.
        import numpy
        import MetaTrader5
        print(json.dumps({"history_provider": MetaTrader5.__version__, "numpy": numpy.__version__, "broker_execution_requested": False}))
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "--collect-history":
        from .history_collect import main as collect_history
        collect_history(sys.argv[2:])
        return 0
    args = build_parser().parse_args()

    try:
        return asyncio.run(run_server(args.host, args.port))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
