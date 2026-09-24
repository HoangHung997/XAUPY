from __future__ import annotations

import asyncio
import os
import time
from typing import Final

from . import __version__
from .contracts import Envelope, PROTOCOL_VERSION, ProtocolError

DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 39421
MAX_LINE_BYTES: Final = 1024 * 1024


class EngineServer:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("XAUPY Engine may bind to loopback only")
        if not (0 <= port <= 65535):
            raise ValueError("port must be between 0 and 65535")

        self.host = "127.0.0.1" if host == "localhost" else host
        self.port = port
        self.bound_port = port
        self._server: asyncio.AbstractServer | None = None
        self._shutdown_event = asyncio.Event()
        self._started_monotonic = time.monotonic()
        self._connections_total = 0

    async def start(self) -> None:
        if self._server is not None:
            return

        self._server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port,
            limit=MAX_LINE_BYTES,
        )

        sockets = self._server.sockets or []
        if not sockets:
            raise RuntimeError("Engine server started without a listening socket")

        self.bound_port = int(sockets[0].getsockname()[1])

    async def wait_for_shutdown(self) -> None:
        await self._shutdown_event.wait()

    async def close(self) -> None:
        if self._server is None:
            return

        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._connections_total += 1

        try:
            while not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break

                if len(line) > MAX_LINE_BYTES:
                    await self._write(
                        writer,
                        Envelope.create(
                            "error",
                            {"code": "MESSAGE_TOO_LARGE", "message": "IPC line exceeded limit"},
                        ),
                    )
                    break

                try:
                    text = line.decode("utf-8").rstrip("\r\n")
                    request = Envelope.from_json(text)
                except (UnicodeDecodeError, ProtocolError) as exc:
                    await self._write(
                        writer,
                        Envelope.create(
                            "error",
                            {"code": "PROTOCOL_ERROR", "message": str(exc)},
                        ),
                    )
                    continue

                response, should_shutdown = self._dispatch(request)
                await self._write(writer, response)

                if should_shutdown:
                    self._shutdown_event.set()
                    break
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, BrokenPipeError):
                pass

    def _dispatch(self, request: Envelope) -> tuple[Envelope, bool]:
        common = {
            "component": "python-engine",
            "engine_version": __version__,
            "protocol_version": PROTOCOL_VERSION,
            "state": "ready",
            "trading_enabled": False,
            "pid": os.getpid(),
        }

        if request.type == "hello":
            return Envelope.response("hello_ack", request.request_id, common), False

        if request.type == "heartbeat":
            payload = {
                **common,
                "uptime_ms": int((time.monotonic() - self._started_monotonic) * 1000),
                "connections_total": self._connections_total,
            }
            return Envelope.response("heartbeat_ack", request.request_id, payload), False

        if request.type == "shutdown":
            return (
                Envelope.response(
                    "shutdown_ack",
                    request.request_id,
                    {**common, "state": "stopping"},
                ),
                True,
            )

        return (
            Envelope.response(
                "error",
                request.request_id,
                {
                    "code": "UNSUPPORTED_MESSAGE",
                    "message": f"Unsupported Task 002 message type: {request.type}",
                    "trading_enabled": False,
                },
            ),
            False,
        )

    @staticmethod
    async def _write(writer: asyncio.StreamWriter, envelope: Envelope) -> None:
        writer.write((envelope.to_json() + "\n").encode("utf-8"))
        await writer.drain()
