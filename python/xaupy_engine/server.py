from __future__ import annotations

import asyncio
import os
import time
from typing import Final

from . import __version__
from .bridge_state import BridgeRegistry, BridgeSnapshotError
from .contracts import Envelope, PROTOCOL_VERSION, ProtocolError
from .config_schema import default_profile, normalized_profile, schema_payload, validate_profile
from .strategy_engine import StrategyEngine
from .execution_simulator import ManualActionSimulator

DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 39421
MAX_LINE_BYTES: Final = 1024 * 1024


class EngineServer:
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        bridge_stale_seconds: float = 5.0,
    ) -> None:
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
        self.bridge = BridgeRegistry(stale_seconds=bridge_stale_seconds)
        self.active_profile = default_profile()
        self.strategy = StrategyEngine(self.active_profile)
        self.manual_actions = ManualActionSimulator(self.bridge)

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

    def _common(self) -> dict:
        return {
            "component": "python-engine",
            "engine_version": __version__,
            "protocol_version": PROTOCOL_VERSION,
            "state": "ready",
            "trading_enabled": False,
            "execution_enabled": False,
            "pid": os.getpid(),
        }

    def _dispatch(self, request: Envelope) -> tuple[Envelope, bool]:
        common = self._common()

        if request.type == "hello":
            return Envelope.response("hello_ack", request.request_id, common), False

        if request.type == "heartbeat":
            bridge_status = self.bridge.status()
            market_connected = bridge_status.connected and bridge_status.terminal_connected
            payload = {
                **common,
                "uptime_ms": int((time.monotonic() - self._started_monotonic) * 1000),
                "connections_total": self._connections_total,
                "bridge": bridge_status.to_payload(),
                "overview": self.bridge.overview_payload(),
                "orders_positions": self.bridge.orders_positions_payload(),
                "strategy": self.strategy.status_payload(
                    market_connected=market_connected
                ),
            }
            return Envelope.response("heartbeat_ack", request.request_id, payload), False

        if request.type == "config_schema_get":
            return (
                Envelope.response(
                    "config_schema_ack",
                    request.request_id,
                    {
                        **common,
                        "config_schema": schema_payload(),
                    },
                ),
                False,
            )

        if request.type == "config_defaults_get":
            return (
                Envelope.response(
                    "config_defaults_ack",
                    request.request_id,
                    {
                        **common,
                        "profile": default_profile(),
                    },
                ),
                False,
            )

        if request.type == "config_active_get":
            return (
                Envelope.response(
                    "config_active_ack",
                    request.request_id,
                    {
                        **common,
                        "profile": normalized_profile(self.active_profile),
                    },
                ),
                False,
            )

        if request.type == "config_active_set":
            profile = request.payload.get("profile")
            if not isinstance(profile, dict):
                return (
                    Envelope.response(
                        "config_active_set_ack",
                        request.request_id,
                        {
                            **common,
                            "applied": False,
                            "errors": ["profile must be an object"],
                        },
                    ),
                    False,
                )

            errors = validate_profile(profile)
            if errors:
                return (
                    Envelope.response(
                        "config_active_set_ack",
                        request.request_id,
                        {
                            **common,
                            "applied": False,
                            "errors": errors,
                        },
                    ),
                    False,
                )

            self.active_profile = normalized_profile(profile)
            self.strategy.set_profile(self.active_profile)
            return (
                Envelope.response(
                    "config_active_set_ack",
                    request.request_id,
                    {
                        **common,
                        "applied": True,
                        "errors": [],
                        "profile": normalized_profile(self.active_profile),
                    },
                ),
                False,
            )

        if request.type == "config_validate":
            profile = request.payload.get("profile")
            if not isinstance(profile, dict):
                return (
                    Envelope.response(
                        "config_validate_ack",
                        request.request_id,
                        {
                            **common,
                            "valid": False,
                            "errors": ["profile must be an object"],
                        },
                    ),
                    False,
                )

            errors = validate_profile(profile)
            payload = {
                **common,
                "valid": not errors,
                "errors": errors,
            }
            if not errors:
                payload["profile"] = normalized_profile(profile)

            return Envelope.response(
                "config_validate_ack",
                request.request_id,
                payload,
            ), False

        if request.type == "bridge_hello":
            previous_bridge = self.bridge.status()
            try:
                self.bridge.record_hello(request.payload)
            except BridgeSnapshotError as exc:
                return self._bridge_error(request, str(exc)), False

            if previous_bridge.snapshots_total > 0 and not previous_bridge.connected:
                self.strategy.reset_setup("BRIDGE_RECONNECTED")

            return (
                Envelope.response(
                    "bridge_hello_ack",
                    request.request_id,
                    {
                        **common,
                        "bridge_protocol": 1,
                        "task": "XAUPY-003",
                        "guardian_reason": "TASK003_EXECUTION_LOCKED",
                    },
                ),
                False,
            )

        if request.type == "bridge_heartbeat":
            try:
                self.bridge.record_heartbeat(request.payload)
            except BridgeSnapshotError as exc:
                return self._bridge_error(request, str(exc)), False

            return (
                Envelope.response(
                    "bridge_heartbeat_ack",
                    request.request_id,
                    {
                        **common,
                        "bridge": self.bridge.status().to_payload(),
                    },
                ),
                False,
            )

        if request.type == "bridge_snapshot":
            previous_bridge = self.bridge.status()
            try:
                self.bridge.record_snapshot(request.payload)
            except BridgeSnapshotError as exc:
                return self._bridge_error(request, str(exc)), False

            bridge_status = self.bridge.status()
            if (
                previous_bridge.snapshots_total > 0
                and not previous_bridge.terminal_connected
                and bridge_status.terminal_connected
            ):
                self.strategy.reset_setup("MARKET_RECONNECTED")

            if bridge_status.terminal_connected:
                strategy_status = self.strategy.ingest_snapshot(request.payload)
            else:
                strategy_status = self.strategy.status_payload(market_connected=False)

            return (
                Envelope.response(
                    "bridge_snapshot_ack",
                    request.request_id,
                    {
                        **common,
                        "accepted": True,
                        "command": None,
                        "bridge": bridge_status.to_payload(),
                        "strategy": strategy_status,
                    },
                ),
                False,
            )

        if request.type == "manual_action_simulate":
            result = self.manual_actions.simulate(request.payload, self.active_profile)
            return (
                Envelope.response(
                    "manual_action_simulate_ack",
                    request.request_id,
                    {**common, **result},
                ),
                False,
            )

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
                    "message": f"Unsupported Task 009 message type: {request.type}",
                    "trading_enabled": False,
                    "execution_enabled": False,
                },
            ),
            False,
        )

    @staticmethod
    def _bridge_error(request: Envelope, message: str) -> Envelope:
        return Envelope.response(
            "error",
            request.request_id,
            {
                "code": "BRIDGE_SNAPSHOT_INVALID",
                "message": message,
                "trading_enabled": False,
                "execution_enabled": False,
            },
        )

    @staticmethod
    async def _write(writer: asyncio.StreamWriter, envelope: Envelope) -> None:
        writer.write((envelope.to_json() + "\n").encode("utf-8"))
        await writer.drain()
