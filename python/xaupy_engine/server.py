from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Final

from . import __version__
from .bridge_state import BridgeRegistry, BridgeSnapshotError
from .contracts import Envelope, PROTOCOL_VERSION, ProtocolError
from .config_schema import (
    default_profile,
    get_path,
    normalized_profile,
    schema_payload,
    validate_profile,
)
from .execution_simulator import ManualActionSimulator
from .journal import JournalSchemaError, StructuredJournal
from .strategy_engine import StrategyEngine

DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 39421
MAX_LINE_BYTES: Final = 1024 * 1024


class EngineServer:
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        bridge_stale_seconds: float = 5.0,
        journal_dir: str | os.PathLike[str] | None = None,
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
        self.journal = StructuredJournal(journal_dir)

        self._last_bridge_connected: bool | None = None
        self._last_market_fresh: bool | None = None
        self._last_strategy_state: str | None = None
        self._last_position_signature: tuple[int, ...] | None = None
        self._last_order_signature: tuple[int, ...] | None = None
        self._last_deal_signature: tuple[int, ...] | None = None
        self._last_market_bar_signature: tuple[tuple[str, int], ...] | None = None
        self._last_decision_trace_signature: tuple[Any, ...] | None = None

        self._log(
            "INFO",
            "Python Engine",
            "SYSTEM",
            "Python Engine initialized",
            details={
                "engine_version": __version__,
                "protocol_version": PROTOCOL_VERSION,
            },
        )

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
        self._log(
            "INFO",
            "Python Engine",
            "CONNECTION",
            f"IPC listening on {self.host}:{self.bound_port}",
            details={"host": self.host, "port": self.bound_port},
        )

    async def wait_for_shutdown(self) -> None:
        await self._shutdown_event.wait()

    async def close(self) -> None:
        if self._server is None:
            return

        self._log(
            "INFO",
            "Python Engine",
            "SYSTEM",
            "Python Engine shutdown requested",
        )
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._connections_total += 1
        peer = writer.get_extra_info("peername")
        self._log(
            "DEBUG",
            "Python Engine",
            "CONNECTION",
            "IPC client connected",
            details={
                "peer": str(peer),
                "connections_total": self._connections_total,
            },
        )

        try:
            while not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break

                if len(line) > MAX_LINE_BYTES:
                    self._log(
                        "ERROR",
                        "Python Engine",
                        "PROTOCOL",
                        "IPC line exceeded maximum size",
                        details={"bytes": len(line)},
                    )
                    await self._write(
                        writer,
                        Envelope.create(
                            "error",
                            {
                                "code": "MESSAGE_TOO_LARGE",
                                "message": "IPC line exceeded limit",
                            },
                        ),
                    )
                    break

                try:
                    text = line.decode("utf-8").rstrip("\r\n")
                    request = Envelope.from_json(text)
                except (UnicodeDecodeError, ProtocolError) as exc:
                    self._log(
                        "ERROR",
                        "Python Engine",
                        "PROTOCOL",
                        f"IPC protocol error: {exc}",
                    )
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
            self._log(
                "DEBUG",
                "Python Engine",
                "CONNECTION",
                "IPC client disconnected",
                details={"peer": str(peer)},
            )
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, BrokenPipeError):
                pass

    def _common(self) -> dict[str, Any]:
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
            self._log(
                "INFO",
                "Python Engine",
                "CONNECTION",
                "Desktop IPC hello accepted",
                details=dict(request.payload),
                correlation_id=request.request_id,
            )
            return Envelope.response("hello_ack", request.request_id, common), False

        if request.type == "heartbeat":
            bridge_status = self.bridge.status()
            market_connected = self.bridge.market_data_connected()
            self._observe_runtime_health(
                bridge_connected=bridge_status.connected,
                market_fresh=market_connected,
            )
            payload = {
                **common,
                "uptime_ms": int(
                    (time.monotonic() - self._started_monotonic) * 1000
                ),
                "connections_total": self._connections_total,
                "bridge": bridge_status.to_payload(),
                "overview": self.bridge.overview_payload(),
                "orders_positions": self.bridge.orders_positions_payload(),
                "strategy": self.strategy.status_payload(
                    market_connected=market_connected
                ),
                "journal_summary": self.journal.summary(date_scope="TODAY"),
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
                errors = ["profile must be an object"]
                self._log(
                    "WARN",
                    "Python Engine",
                    "CONFIG",
                    "Active configuration rejected",
                    details={"errors": errors},
                    correlation_id=request.request_id,
                )
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

            errors = validate_profile(profile)
            if errors:
                self._log(
                    "WARN",
                    "Python Engine",
                    "CONFIG",
                    "Active configuration rejected",
                    details={"errors": errors},
                    correlation_id=request.request_id,
                )
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
            symbol = self.active_profile.get("strategy", {}).get("symbol")
            self._log(
                "INFO",
                "Strategy",
                "CONFIG",
                "Active strategy profile applied",
                details={
                    "profile_name": self.active_profile.get(
                        "profile", {}
                    ).get("name"),
                    "timeframes": self.active_profile.get("timeframes", {}),
                    "symbol": symbol,
                },
                correlation_id=request.request_id,
                symbol=symbol,
            )
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

            self._log(
                "INFO",
                "EA Bridge",
                "CONNECTION",
                "EA Bridge hello accepted",
                details=dict(request.payload),
                correlation_id=request.request_id,
                symbol=request.payload.get("symbol"),
            )

            if previous_bridge.snapshots_total > 0 and not previous_bridge.connected:
                self.strategy.reset_setup("BRIDGE_RECONNECTED")
                self._log(
                    "INFO",
                    "Strategy",
                    "CONNECTION",
                    "Strategy setup reset after Bridge reconnect",
                    details={"reason": "BRIDGE_RECONNECTED"},
                    correlation_id=request.request_id,
                    symbol=request.payload.get("symbol"),
                )

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
                self._log(
                    "INFO",
                    "Strategy",
                    "CONNECTION",
                    "Strategy setup reset after market reconnect",
                    details={"reason": "MARKET_RECONNECTED"},
                    correlation_id=request.request_id,
                    symbol=request.payload.get("symbol"),
                )

            if bridge_status.terminal_connected:
                strategy_status = self.strategy.ingest_snapshot(request.payload)
            else:
                strategy_status = self.strategy.status_payload(
                    market_connected=False
                )

            self._record_bridge_snapshot_evidence(
                request,
                market_connected=(
                    bridge_status.connected
                    and bridge_status.terminal_connected
                    and self.bridge.snapshot_fresh()
                ),
                strategy_status=strategy_status,
            )

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
            result = self.manual_actions.simulate(
                request.payload,
                self.active_profile,
            )
            intent_id = request.payload.get("intent_id")
            action = str(request.payload.get("action", "UNKNOWN"))
            accepted = bool(result.get("accepted", False))
            correlation_id = (
                str(intent_id)
                if intent_id is not None
                else request.request_id
            )
            fresh = self.bridge.latest_fresh_snapshot() or {}
            self._log(
                "INFO" if accepted else "WARN",
                "Orders",
                "ORDER",
                (
                    f"Manual action simulation {action}: "
                    f"{result.get('code', 'UNKNOWN')}"
                ),
                details={
                    "request": dict(request.payload),
                    "result": result,
                },
                correlation_id=correlation_id,
                symbol=fresh.get("symbol"),
            )
            if not accepted and result.get("code") in {
                "STALE_MARKET_DATA",
                "DEMO_ONLY",
                "SAFETY_PROFILE_INVALID",
                "NEVER_WIDEN_SL",
                "SERVER_SL_REQUIRED",
                "DAILY_LOSS_LIMIT",
                "MAX_OPEN_POSITIONS",
            }:
                self._log(
                    "WARN",
                    "Alerts",
                    "RISK",
                    (
                        f"Safety guard blocked {action}: "
                        f"{result.get('code', 'UNKNOWN')}"
                    ),
                    details={"result": result},
                    correlation_id=correlation_id,
                    symbol=fresh.get("symbol"),
                )
            return (
                Envelope.response(
                    "manual_action_simulate_ack",
                    request.request_id,
                    {**common, **result},
                ),
                False,
            )

        if request.type == "journal_query":
            return self._journal_query_response(request, common), False

        if request.type == "journal_bookmark_set":
            return self._journal_bookmark_response(request, common), False

        if request.type == "shutdown":
            self._log(
                "INFO",
                "System",
                "SYSTEM",
                "Desktop requested Engine shutdown",
                details=dict(request.payload),
                correlation_id=request.request_id,
            )
            return (
                Envelope.response(
                    "shutdown_ack",
                    request.request_id,
                    {**common, "state": "stopping"},
                ),
                True,
            )

        self._log(
            "WARN",
            "Python Engine",
            "PROTOCOL",
            f"Unsupported message type: {request.type}",
            details={"type": request.type},
            correlation_id=request.request_id,
        )
        return (
            Envelope.response(
                "error",
                request.request_id,
                {
                    "code": "UNSUPPORTED_MESSAGE",
                    "message": (
                        f"Unsupported Task 010 message type: {request.type}"
                    ),
                    "trading_enabled": False,
                    "execution_enabled": False,
                },
            ),
            False,
        )

    def _journal_query_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            levels = request.payload.get("levels")
            sources = request.payload.get("sources")
            if levels is not None and not isinstance(levels, list):
                raise JournalSchemaError("levels must be an array")
            if sources is not None and not isinstance(sources, list):
                raise JournalSchemaError("sources must be an array")

            before_sequence = request.payload.get("before_sequence")
            if before_sequence is not None and (
                isinstance(before_sequence, bool)
                or not isinstance(before_sequence, int)
            ):
                raise JournalSchemaError(
                    "before_sequence must be integer or null"
                )

            result = self.journal.query(
                levels=levels,
                sources=sources,
                search=request.payload.get("search"),
                date_scope=str(
                    request.payload.get("date_scope", "TODAY")
                ),
                bookmarks_only=bool(
                    request.payload.get("bookmarks_only", False)
                ),
                limit=int(request.payload.get("limit", 500)),
                before_sequence=before_sequence,
            )
            summary = self.journal.summary(
                date_scope=str(
                    request.payload.get("date_scope", "TODAY")
                )
            )
            payload = {
                **common,
                "ok": True,
                "journal": result,
                "summary": summary,
            }
        except (JournalSchemaError, TypeError, ValueError) as exc:
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }

        return Envelope.response(
            "journal_query_ack",
            request.request_id,
            payload,
        )

    def _journal_bookmark_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            sequence = request.payload.get("sequence")
            bookmarked = request.payload.get("bookmarked")
            if isinstance(sequence, bool) or not isinstance(sequence, int):
                raise JournalSchemaError(
                    "bookmark sequence must be an integer"
                )
            if not isinstance(bookmarked, bool):
                raise JournalSchemaError(
                    "bookmarked must be boolean"
                )

            event = self.journal.set_bookmark(sequence, bookmarked)
            payload = {
                **common,
                "ok": True,
                "event": event,
                "summary": self.journal.summary(date_scope="TODAY"),
            }
        except (JournalSchemaError, TypeError, ValueError) as exc:
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }

        return Envelope.response(
            "journal_bookmark_set_ack",
            request.request_id,
            payload,
        )

    def _record_bridge_snapshot_evidence(
        self,
        request: Envelope,
        *,
        market_connected: bool,
        strategy_status: dict[str, Any],
    ) -> None:
        snapshot = request.payload
        symbol = snapshot.get("symbol")

        decision_trace_enabled = self._decision_trace_enabled()
        market_bar_signature = self._bar_time_signature(snapshot.get("bars"))
        if (
            decision_trace_enabled
            and market_bar_signature != self._last_market_bar_signature
        ):
            self._log(
                "DEBUG",
                "MT5",
                "MARKET_DATA",
                f"Closed-bar snapshot advanced for {symbol or '?'}",
                details={
                    "bar_times": dict(market_bar_signature),
                    "bid": snapshot.get("bid"),
                    "ask": snapshot.get("ask"),
                    "spread_points": snapshot.get("spread_points"),
                    "positions_count": snapshot.get("positions_count"),
                    "orders_count": snapshot.get("orders_count"),
                    "market_connected": market_connected,
                },
                correlation_id=request.request_id,
                symbol=symbol,
            )
            self._last_market_bar_signature = market_bar_signature

        state = str(strategy_status.get("state", "STALE"))
        if state != self._last_strategy_state:
            self._log(
                "INFO",
                "Strategy",
                "STRATEGY",
                f"Strategy state -> {state}",
                details={
                    "previous_state": self._last_strategy_state,
                    "state": state,
                    "blocked_reason": strategy_status.get("blocked_reason"),
                    "direction": strategy_status.get("direction"),
                    "armed_side": strategy_status.get("armed_side"),
                    "timeframes": strategy_status.get("timeframes", {}),
                    "indicators": strategy_status.get("indicators", {}),
                    "conditions": strategy_status.get("conditions", {}),
                    "signal_sequence": strategy_status.get(
                        "signal_sequence"
                    ),
                },
                correlation_id=request.request_id,
                symbol=symbol,
                profile_hash=strategy_status.get("profile_hash"),
            )
            self._last_strategy_state = state

        decision_trace_signature = (
            state,
            strategy_status.get("last_evaluated_trigger_time"),
            strategy_status.get("signal_sequence"),
            strategy_status.get("blocked_reason"),
            strategy_status.get("direction"),
            strategy_status.get("armed_side"),
        )
        if (
            decision_trace_enabled
            and decision_trace_signature != self._last_decision_trace_signature
        ):
            self._log(
                "DEBUG",
                "Strategy",
                "DECISION_TRACE",
                f"Strategy evaluation: {state}",
                details={
                    "state": state,
                    "blocked_reason": strategy_status.get("blocked_reason"),
                    "direction": strategy_status.get("direction"),
                    "armed_side": strategy_status.get("armed_side"),
                    "bars_seen": strategy_status.get("bars_seen", {}),
                    "indicators": strategy_status.get("indicators", {}),
                    "conditions": strategy_status.get("conditions", {}),
                    "last_signal": strategy_status.get("last_signal"),
                },
                correlation_id=request.request_id,
                symbol=symbol,
                profile_hash=strategy_status.get("profile_hash"),
            )
            self._last_decision_trace_signature = decision_trace_signature

        position_signature = self._ticket_signature(
            snapshot.get("positions")
        )
        order_signature = self._ticket_signature(
            snapshot.get("orders")
        )
        deal_signature = self._ticket_signature(
            snapshot.get("deals")
        )
        if (
            position_signature != self._last_position_signature
            or order_signature != self._last_order_signature
            or deal_signature != self._last_deal_signature
        ):
            self._log(
                "INFO",
                "Orders",
                "POSITION",
                "Owned trade state changed",
                details={
                    "positions": list(position_signature),
                    "orders": list(order_signature),
                    "deals": list(deal_signature),
                    "positions_count": len(position_signature),
                    "orders_count": len(order_signature),
                },
                correlation_id=request.request_id,
                symbol=symbol,
            )
            self._last_position_signature = position_signature
            self._last_order_signature = order_signature
            self._last_deal_signature = deal_signature

    def _observe_runtime_health(
        self,
        *,
        bridge_connected: bool,
        market_fresh: bool,
    ) -> None:
        if self._last_bridge_connected is None:
            self._last_bridge_connected = bridge_connected
        elif bridge_connected != self._last_bridge_connected:
            self._log(
                "INFO" if bridge_connected else "WARN",
                "EA Bridge" if bridge_connected else "Alerts",
                "CONNECTION",
                (
                    "EA Bridge reconnected"
                    if bridge_connected
                    else "EA Bridge disconnected"
                ),
                details={"connected": bridge_connected},
            )
            self._last_bridge_connected = bridge_connected

        if self._last_market_fresh is None:
            self._last_market_fresh = market_fresh
        elif market_fresh != self._last_market_fresh:
            self._log(
                "INFO" if market_fresh else "WARN",
                "EA Bridge" if market_fresh else "Alerts",
                "MARKET_DATA" if market_fresh else "MARKET_DATA_STALE",
                (
                    "Market snapshot is fresh"
                    if market_fresh
                    else "Market snapshot became stale"
                ),
                details={"market_fresh": market_fresh},
            )
            self._last_market_fresh = market_fresh

    def _decision_trace_enabled(self) -> bool:
        try:
            return bool(
                get_path(
                    self.active_profile,
                    "logging.decision_trace_enabled",
                )
            )
        except KeyError:
            return True

    @staticmethod
    def _bar_time_signature(value: object) -> tuple[tuple[str, int], ...]:
        if not isinstance(value, dict):
            return ()
        result: list[tuple[str, int]] = []
        for timeframe, bar in value.items():
            if not isinstance(timeframe, str) or not isinstance(bar, dict):
                continue
            timestamp = bar.get("time")
            if isinstance(timestamp, int) and not isinstance(timestamp, bool):
                result.append((timeframe, timestamp))
        return tuple(sorted(result))

    @staticmethod
    def _ticket_signature(value: object) -> tuple[int, ...]:
        if not isinstance(value, list):
            return ()
        tickets: list[int] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            ticket = item.get("ticket")
            if isinstance(ticket, int) and not isinstance(ticket, bool):
                tickets.append(ticket)
        return tuple(sorted(tickets))

    def _log(
        self,
        level: str,
        source: str,
        tag: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        symbol: str | None = None,
        profile_hash: str | None = None,
    ) -> None:
        try:
            self.journal.append(
                level,
                source,
                tag,
                message,
                details=details,
                correlation_id=correlation_id,
                symbol=symbol,
                profile_hash=profile_hash,
            )
        except (OSError, JournalSchemaError, TypeError, ValueError):
            # Evidence logging must never crash Engine/execution control.
            pass

    def _bridge_error(
        self,
        request: Envelope,
        message: str,
    ) -> Envelope:
        self._log(
            "ERROR",
            "EA Bridge",
            "DATA",
            f"Bridge snapshot rejected: {message}",
            details={"message_type": request.type},
            correlation_id=request.request_id,
            symbol=request.payload.get("symbol"),
        )
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
    async def _write(
        writer: asyncio.StreamWriter,
        envelope: Envelope,
    ) -> None:
        writer.write((envelope.to_json() + "\n").encode("utf-8"))
        await writer.drain()
