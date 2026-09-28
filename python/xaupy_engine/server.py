from __future__ import annotations

from copy import deepcopy
import asyncio
import json
import os
import sqlite3
from pathlib import Path
import time
from typing import Any, Final
from uuid import UUID

from . import __version__
from .backtest import (
    BacktestEngine,
    BacktestError,
    BacktestRepository,
    load_historical_dataset,
)
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
from .optimizer import (
    OptimizerError,
    OptimizerJobManager,
    OptimizerRepository,
    heatmap_from_result,
)
from .strategy_engine import StrategyEngine, StrategyDataError
from .settings import SettingsStore, default_settings
from .diagnostics import collect_diagnostics
from .history_jobs import HistoryJobs
from .broker_history_jobs import BrokerHistoryJobs
from .user_library import UserLibrary
from .backtest_jobs import BacktestJobs
from .tick_protocol import TickTransport, validate_tick_payload
from .demo_once import DemoOnceController, DemoOnceError, UnavailableDemoOnceController, profile_hash
from .broker_execution import BrokerExecution, UnavailableBrokerExecution
from .trade_plan import TradePlanError
from .monitoring import MonitoringService

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
        backtest_dir: str | os.PathLike[str] | None = None,
        optimizer_dir: str | os.PathLike[str] | None = None,
        state_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("XAUPY Engine may bind to loopback only")
        if not (0 <= port <= 65535):
            raise ValueError("port must be between 0 and 65535")

        self.host = "127.0.0.1" if host == "localhost" else host
        self.port = port
        self.bound_port = port
        self._server: asyncio.AbstractServer | None = None
        self._client_writers: set[asyncio.StreamWriter] = set()
        self._shutdown_event = asyncio.Event()
        self._started_monotonic = time.monotonic()
        self._connections_total = 0
        self.instance_id = os.environ.get("XAUPY_INSTANCE_ID", "")
        self.bridge = BridgeRegistry(stale_seconds=bridge_stale_seconds)
        self.tick_transport = TickTransport()
        # An explicitly scoped server must not send its other stores back to the
        # signed-in user's production directories. In particular, protocol tests
        # historically supplied only state_dir and polluted the real journal.
        scoped_root = next((Path(value) for value in
                            (state_dir, journal_dir, backtest_dir, optimizer_dir)
                            if value is not None), None)
        if scoped_root is not None:
            journal_dir = journal_dir if journal_dir is not None else scoped_root / "logs"
            backtest_dir = backtest_dir if backtest_dir is not None else scoped_root / "backtests"
            optimizer_dir = optimizer_dir if optimizer_dir is not None else scoped_root / "optimizer"
        self.settings_store = SettingsStore(state_dir if state_dir is not None else
                                            Path(journal_dir) / "state" if journal_dir is not None else None)
        self.active_profile = deepcopy(self.settings_store.profile)
        self.library = UserLibrary(self.settings_store.root_dir)
        try:
            startup_profile=self.library.startup_profile()
            if startup_profile is not None:
                if self.active_profile != startup_profile:
                    self.settings_store.save(profile=startup_profile)
                self.active_profile=deepcopy(startup_profile)
                self.settings_store.recovery_message += '; explicit startup profile selected'
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.settings_store.recovery_message += '; startup profile rejected: '+str(exc)
        self.history_jobs = HistoryJobs(self.settings_store.root_dir)
        self.broker_history_jobs = BrokerHistoryJobs(self.settings_store.root_dir)
        self.strategy = StrategyEngine(self.active_profile)
        try:
            self.execution = BrokerExecution(self.settings_store.root_dir, self.bridge, self.strategy, self.settings_store.settings)
            self.execution.snapshot_transform = self.library.merge_calendar
        except (sqlite3.Error, OSError, ValueError) as exc:
            self.execution = UnavailableBrokerExecution(exc)
        self.strategy.observation_callback = self._on_strategy_observation
        try:
            self.demo_once = DemoOnceController(self.settings_store.root_dir, self.bridge, self.strategy)
        except (DemoOnceError, OSError) as exc:
            # A damaged authorization ledger must disable execution without
            # taking market monitoring and diagnostics offline.
            self.demo_once = UnavailableDemoOnceController(str(exc))
        self._demo_bridge_writer: asyncio.StreamWriter | None = None
        self.manual_actions = ManualActionSimulator(self.bridge)
        self.journal = StructuredJournal(journal_dir)
        from .mt5_logs import Mt5LogReader
        self.mt5_logs = Mt5LogReader(self.settings_store.root_dir,self.journal)
        self.monitoring = MonitoringService(self.settings_store.root_dir)
        self.backtests = BacktestRepository(backtest_dir)
        self.backtest_jobs = BacktestJobs(self.backtests, self._log)
        self.optimizers = OptimizerRepository(optimizer_dir)
        from .data_transfer import DataTransfer
        self.data_transfer=DataTransfer(self.settings_store.root_dir,self.journal.root_dir,self.backtests.root_dir,self.optimizers.root_dir)
        self.optimizer_jobs = OptimizerJobManager(
            self.optimizers,
            journal_callback=self._optimizer_journal,
        )

        self._last_bridge_connected: bool | None = None
        self._last_market_fresh: bool | None = None
        self._last_strategy_state: str | None = None
        self._last_position_signature: tuple[int, ...] | None = None
        self._last_order_signature: tuple[int, ...] | None = None
        self._last_deal_signature: tuple[int, ...] | None = None
        self._last_market_bar_signature: tuple[tuple[str, int], ...] | None = None
        self._last_decision_trace_signature: tuple[Any, ...] | None = None
        self._last_demo_result_log: tuple[str, float] | None = None

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
        await asyncio.to_thread(self.data_transfer.close)
        await asyncio.to_thread(self.mt5_logs.close)
        await asyncio.to_thread(self.backtest_jobs.close)
        await asyncio.to_thread(self.history_jobs.close)
        await asyncio.to_thread(self.broker_history_jobs.close)
        optimizer_stopped = await asyncio.to_thread(
            self.optimizer_jobs.shutdown,
            5.0,
        )
        if not optimizer_stopped:
            self._log(
                "WARN",
                "Python Engine",
                "OPTIMIZER_SHUTDOWN",
                "Optimizer threads did not stop within shutdown timeout",
            )

        if self._server is None:
            self.execution.close()
            return

        self._log(
            "INFO",
            "Python Engine",
            "SYSTEM",
            "Python Engine shutdown requested",
        )
        server = self._server
        self._server = None
        server.close()

        # Python 3.13 Server.wait_closed() waits for active connections too.
        # Engine shutdown must therefore close current Desktop/Bridge sockets
        # explicitly instead of waiting forever for clients to disconnect.
        writers = list(self._client_writers)
        for writer in writers:
            if not writer.is_closing():
                writer.close()

        if writers:
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        *(writer.wait_closed() for writer in writers),
                        return_exceptions=True,
                    ),
                    timeout=2.0,
                )
            except TimeoutError:
                self._log(
                    "WARN",
                    "Python Engine",
                    "CONNECTION",
                    "Timed out draining client sockets during shutdown",
                    details={"writers": len(writers)},
                )

        try:
            await asyncio.wait_for(
                server.wait_closed(),
                timeout=2.0,
            )
        except TimeoutError:
            self._log(
                "WARN",
                "Python Engine",
                "CONNECTION",
                "Timed out waiting for IPC server close",
            )

        self.execution.close()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._connections_total += 1
        self._client_writers.add(writer)
        peer = writer.get_extra_info("peername")
        bridge_session_id: str | None = None
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

                # The bounded demo command may only leave on the connection
                # which established the current capable EA session. Desktop and
                # diagnostic sockets cannot collect commands or report fills.
                candidate_session = None
                if (request.type == "bridge_hello" and self._demo_bridge_writer is not None
                        and self._demo_bridge_writer is not writer):
                    await self._write(writer, self._bridge_error(request, "A capable Bridge connection already owns the session"))
                    continue
                if request.type == "bridge_hello" and request.payload.get("demo_once_capable") is True:
                    try:
                        candidate_session = str(UUID(request.payload.get("bridge_session_id", "")))
                    except (ValueError, TypeError, AttributeError):
                        await self._write(writer, self._bridge_error(request, "Invalid demo Bridge session"))
                        continue
                    if (request.payload.get("component") != "mt5-bridge"
                            or self._demo_bridge_writer not in (None, writer)):
                        await self._write(writer, self._bridge_error(request, "A capable Bridge connection already owns the session"))
                        continue
                if (request.type.startswith("bridge_") and request.type != "bridge_hello"
                        and self._demo_bridge_writer is not None
                        and self._demo_bridge_writer is not writer):
                    await self._write(writer, self._bridge_error(request, "Bridge messages require the owning connection"))
                    continue
                if (request.type == "bridge_snapshot" and bridge_session_id is not None
                        and str(request.payload.get("bridge_session_id", "")).lower() != bridge_session_id):
                    await self._write(writer, self._bridge_error(request, "Bridge snapshot session changed"))
                    continue
                if request.type == "backtest_run":
                    response = await self._legacy_backtest_async(request)
                    should_shutdown = False
                elif request.type == "backtest_dataset_inspect":
                    response = await asyncio.to_thread(self._backtest_dataset_inspect_response, request, self._common())
                    should_shutdown = False
                elif request.type in {'optimizer_start','research_start','walk_forward_start'}:
                    handler=self._walk_forward_start_response if request.type=='walk_forward_start' else self._optimizer_start_response
                    response=await asyncio.to_thread(handler,request,self._common())
                    should_shutdown=False
                else:
                    try:
                        response, should_shutdown = self._dispatch(request, bridge_session_id=bridge_session_id)
                    except (sqlite3.Error, OSError) as exc:
                        self._disable_execution(exc)
                        response = Envelope.response('error',request.request_id,{'code':'EXECUTION_STORAGE_UNAVAILABLE','message':str(exc)})
                        should_shutdown = False
                if candidate_session is not None and response.type == "bridge_hello_ack":
                    bridge_session_id = candidate_session
                    self._demo_bridge_writer = writer
                await self._write(writer, response)

                if should_shutdown:
                    self._shutdown_event.set()
                    break
        finally:
            if self._demo_bridge_writer is writer:
                self._demo_bridge_writer = None
                try:
                    self.execution.disconnected()
                except (sqlite3.Error, OSError) as exc:
                    self._disable_execution(exc)
            self._client_writers.discard(writer)
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

    def _demo_once_command(self, bridge_session_id: str | None) -> dict[str, Any] | None:
        if self.execution.policy['mode'] != 'OFF':
            return None
        snapshot = self.bridge.latest_fresh_snapshot() or {}
        if (bridge_session_id is None or snapshot.get("demo_once_capable") is not True
                or str(snapshot.get("bridge_session_id", "")).lower() != bridge_session_id):
            return None
        command = self.demo_once.on_signal(self.active_profile)
        if command is not None:
            self._log("WARN", "Orders", "DEMO_ONCE",
                      "One DEMO command durably dispatched; no automatic retry",
                      details=command, correlation_id=command.get("attempt_id"), symbol=command.get("symbol"))
        return command

    def _on_strategy_observation(self):
        if self._demo_bridge_writer is not None:
            self.execution.manage_positions(self.active_profile)
            self.execution.observe_signal(self.active_profile)

    def _demo_result_session_matches(self, payload: dict[str, Any], bridge_session_id: str | None) -> bool:
        if bridge_session_id is None:
            return False
        original_session = str(payload.get("bridge_session_id", "")).lower()
        if original_session == bridge_session_id:
            return True
        # A restarted EA can replay the *result* of its original command, never
        # the command itself. Bind this read-only reconciliation to the stored
        # authorization and a fresh snapshot from the current owning EA socket.
        authorization = self.demo_once.status().get("authorization") or {}
        snapshot = self.bridge.latest_fresh_snapshot() or {}
        return (original_session == str(authorization.get("bridge_session_id", "")).lower()
                and str(snapshot.get("bridge_session_id", "")).lower() == bridge_session_id
                and snapshot.get("account_trade_mode") == "DEMO"
                and snapshot.get("demo_once_capable") is True
                and payload.get("attempt_id") == authorization.get("attempt_id")
                and all(snapshot.get(key) == payload.get(key) == authorization.get(key)
                        and snapshot.get(key) is not None
                        for key in ("account_login", "account_server", "symbol", "magic")))

    def _common(self) -> dict[str, Any]:
        self.execution.settings = self.settings_store.settings
        try:
            status = self.execution.status()
        except (sqlite3.Error, OSError) as exc:
            self._disable_execution(exc)
            status = self.execution.status()
        return {
            "component": "python-engine",
            "engine_version": __version__,
            "protocol_version": PROTOCOL_VERSION,
            "state": "ready",
            "trading_enabled": status['trading_enabled'],
            "execution_enabled": status['execution_enabled'],
            "execution_capable": True,
            "pid": os.getpid(),
            "engine_instance_id": self.instance_id,
        }

    def _disable_execution(self, exc):
        try:
            self.execution.close()
        except (sqlite3.Error,OSError):
            pass
        self.execution=UnavailableBrokerExecution(exc)
        self._log('ERROR','Orders','EXECUTION_STORAGE','Execution evidence storage unavailable; existing files preserved',details={'error':str(exc)})

    def _dispatch(self, request: Envelope, *, bridge_session_id: str | None = None) -> tuple[Envelope, bool]:
        common = self._common()

        if request.type in {'execution_status', 'execution_history', 'execution_mode_set', 'execution_action', 'bridge_execution_result'}:
            try:
                if request.type == 'execution_mode_set':
                    if request.payload.get('mode') != 'OFF' and self.demo_once.status().get('state') in {'ARMED','DISPATCHED','UNKNOWN'}:
                        raise TradePlanError('LEGACY_DEMO_ATTEMPT_UNRESOLVED')
                    result = {'accepted':True, **self.execution.set_mode(request.payload, self.active_profile)}
                elif request.type == 'execution_action':
                    result = self.execution.submit(request.payload, self.active_profile)
                elif request.type == 'bridge_execution_result':
                    if bridge_session_id is None:
                        raise TradePlanError('BRIDGE_SESSION_REQUIRED')
                    result = self.execution.record_result(request.payload, bridge_session_id)
                elif request.type == 'execution_history':
                    result = {'accepted':True, 'items':self.execution.history(request.payload.get('limit',100), request.payload.get('offset',0))}
                else:
                    result = {'accepted':True, **self.execution.status()}
            except (TradePlanError, ValueError, TypeError) as exc:
                result = {'accepted':False,'code':str(exc)}
            if request.type not in {'execution_status','execution_history'}:
                self._log('INFO' if result.get('accepted') else 'WARN', 'Orders', 'EXECUTION', request.type,
                          details={'request':request.payload,'result':result}, correlation_id=request.request_id)
            return Envelope.response(request.type+'_ack', request.request_id, {**self._common(), **result}), False

        if request.type in {"demo_once_arm", "demo_once_status", "demo_once_cancel", "bridge_demo_once_result"}:
            if request.type == "demo_once_arm":
                if self.execution.policy['mode'] != 'OFF':
                    result = {**self.demo_once.status(), "accepted": False, "code": "GENERAL_EXECUTION_ACTIVE"}
                elif self._demo_bridge_writer is None:
                    result = {**self.demo_once.status(), "accepted": False, "code": "BRIDGE_SESSION_REQUIRED"}
                else:
                    result = self.demo_once.arm(request.payload, self.active_profile)
            elif request.type == "demo_once_cancel":
                result = self.demo_once.cancel(request.payload)
            elif request.type == "bridge_demo_once_result":
                if not self._demo_result_session_matches(request.payload, bridge_session_id):
                    result = {**self.demo_once.status(), "accepted": False, "code": "BRIDGE_SESSION_REQUIRED"}
                else:
                    result = self.demo_once.record_result(request.payload)
            else:
                result = self.demo_once.status()
            log_result = request.type != "demo_once_status"
            if request.type == "bridge_demo_once_result":
                # A retained EA result may belong to a different local runtime.
                # Still validate and reply on every replay, but do not flood
                # the journal/toasts with the same refusal on every timer tick.
                signature = json.dumps([request.payload, result.get('state'), result.get('code'),
                                        result.get('accepted', False)], sort_keys=True)
                now = time.monotonic()
                previous = self._last_demo_result_log
                log_result = previous is None or previous[0] != signature or now-previous[1] >= 60
                if log_result:
                    self._last_demo_result_log = (signature, now)
            if log_result:
                self._log("INFO" if result.get("accepted", False) else "WARN", "Orders", "DEMO_ONCE",
                          f"Demo one-shot {request.type}: {result.get('state', '?')} / {result.get('code', '')}",
                          details=result, correlation_id=request.request_id)
            snapshot = self.bridge.latest_fresh_snapshot() or {}
            context = {key: snapshot.get(key) for key in
                       ("account_trade_mode", "account_login", "account_server", "symbol", "magic",
                        "bridge_session_id", "demo_once_capable", "demo_once_guard")}
            context["profile_hash"] = profile_hash(self.active_profile)
            return Envelope.response(request.type + "_ack", request.request_id,
                                     {**common, "accepted": result.get("accepted", False),
                                      "demo_once": result, "demo_once_context": context}), False

        if request.type in {"diagnostics_get", "settings_get", "settings_defaults_get", "settings_set",
                            "backup_create", "backup_restore", "history_download_start", "history_download_status",
                            "broker_history_start", "broker_history_status", "broker_history_query",
                            "history_catalog", "library_profile_list", "library_profile_save", "library_profile_get",
                            "calendar_import", "calendar_validate", "calendar_get", "startup_profile_set", "startup_profile_clear", "optimizer_candidate_prepare",
                            "data_transfer_start", "data_transfer_status", "data_transfer_cancel"}:
            return self._maintenance_response(request, common), False

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

        if request.type in {"heartbeat", "market_update"}:
            full = request.type == "heartbeat"
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
                "tick_transport": self.tick_transport.payload(),
                "demo_once": self.demo_once.status(),
                "execution": self.execution.status(),
                "overview": self.bridge.overview_payload(include_history=full),
                "orders_positions": self.bridge.orders_positions_payload(),
                "strategy": self.strategy.status_payload(
                    market_connected=market_connected
                ),
            }
            display = payload["strategy"].get("display", {})
            overview = payload["overview"]
            if overview.get("available") and display.get("available"):
                timestamp = display.get("tick_time_msc", 0)
                # A late display packet must never move a newer snapshot quote backward.
                if timestamp >= (overview.get("tick_time_msc") or 0):
                    overview.update(bid=display["bid"], ask=display["ask"], tick_time_msc=timestamp)
                    if overview.get("point"):
                        overview["spread_points"] = (display["ask"] - display["bid"]) / overview["point"]
                    payload["orders_positions"].update(bid=display["bid"], ask=display["ask"],
                                                       spread_points=overview.get("spread_points"))
                overview["forming_bars"] = {tf: {**bar, "tick_volume": bar["observed_ticks"]}
                                            for tf, bar in display.get("current_bars", {}).items()}
                overview["forming_bars_partial"] = True
            if full:
                payload['monitoring'] = self.monitoring.payload(self)
                payload["journal_summary"] = self.journal.summary(date_scope="TODAY")
                payload["optimizer_status"] = self.optimizer_jobs.status()
            return Envelope.response(request.type + "_ack", request.request_id, payload), False

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
            expected = request.payload.get("expected_profile")
            if expected is not None and expected != self.active_profile:
                return Envelope.response("config_active_set_ack", request.request_id, {
                    **common, "applied": False,
                    "errors": ["Cấu hình đang chạy đã thay đổi. Bản nháp được giữ; lưu bản nháp rồi tải lại trước khi áp dụng."],
                }), False
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

            try:
                self.settings_store.save(profile=profile)
            except (OSError, ValueError, TypeError) as exc:
                return Envelope.response("config_active_set_ack", request.request_id,
                                         {**common, "applied": False, "errors": [str(exc)]}), False
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
                        "guardian_reason": "USER_CONTROLLED",
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
            previously_fresh = self.bridge.market_data_connected()
            try:
                self.bridge.record_snapshot(request.payload)
            except BridgeSnapshotError as exc:
                return self._bridge_error(request, str(exc)), False

            bridge_status = self.bridge.status()
            if (
                previous_bridge.snapshots_total > 0
                and not previously_fresh
                and bridge_status.terminal_connected
            ):
                self.strategy.reset_setup("MARKET_RECONNECTED" if not previous_bridge.terminal_connected else "MARKET_DATA_STALE")
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
            self.execution.on_snapshot()
            if bridge_session_id is not None:
                self.execution.manage_positions(self.active_profile)
                self.execution.observe_signal(self.active_profile)

            return (
                Envelope.response(
                    "bridge_snapshot_ack",
                    request.request_id,
                    {
                        **self._common(),
                        "accepted": True,
                        "command": None,
                        "execution_command": self.execution.next_command(self.active_profile, bridge_session_id) if bridge_session_id else None,
                        "demo_once_command": self._demo_once_command(bridge_session_id),
                        "bridge": bridge_status.to_payload(),
                        "strategy": strategy_status,
                    },
                ),
                False,
            )

        if request.type == "bridge_ticks":
            try:
                validate_tick_payload(request.payload)
            except ValueError as exc:
                return self._bridge_error(request, str(exc)), False
            fresh = self.bridge.market_data_connected()
            matching = (request.payload["symbol"] == self.bridge.status().symbol
                        and request.payload["symbol"] == self.active_profile["strategy"]["symbol"])
            if not fresh or not matching:
                self.strategy.reset_setup("MARKET_DATA_STALE" if not fresh else "TICK_SYMBOL_MISMATCH")
                status = self.strategy.status_payload(market_connected=fresh)
            else:
                try:
                    status = self.strategy.ingest_tick_batch(request.payload)
                except StrategyDataError as exc:
                    self.strategy.reset_setup("INVALID_TICK_BATCH")
                    return self._bridge_error(request, str(exc)), False
                self.tick_transport.record_accepted(request.payload)
                if bridge_session_id is not None:
                    self.execution.observe_signal(self.active_profile)
            return Envelope.response("bridge_ticks_ack", request.request_id,
                                     {**self._common(), "accepted": fresh and matching, "command": None,
                                      "execution_command": self.execution.next_command(self.active_profile, bridge_session_id) if bridge_session_id and fresh and matching else None,
                                      "demo_once_command": self._demo_once_command(bridge_session_id) if fresh and matching else None,
                                      "tick_transport": self.tick_transport.payload(), "strategy": status}), False

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

        if request.type == "backtest_dataset_inspect":
            return self._backtest_dataset_inspect_response(request, common), False

        if request.type in {"backtest_start", "backtest_status", "backtest_cancel"}:
            return self._backtest_job_response(request, common), False

        if request.type == "backtest_history_query":
            return self._backtest_history_response(request, common), False

        if request.type == "backtest_result_get":
            return self._backtest_result_get_response(request, common), False

        if request.type == "backtest_result_delete":
            return self._backtest_result_delete_response(request, common), False

        if request.type in {"optimizer_start", "research_start"}:
            return self._optimizer_start_response(request, common), False

        if request.type == "walk_forward_start":
            return self._walk_forward_start_response(request, common), False

        if request.type == "optimizer_status":
            return self._optimizer_status_response(request, common), False

        if request.type == "optimizer_cancel":
            return self._optimizer_cancel_response(request, common), False

        if request.type == "optimizer_result_get":
            return self._optimizer_result_get_response(request, common), False

        if request.type == "optimizer_history_query":
            return self._optimizer_history_response(request, common), False

        if request.type == "optimizer_result_delete":
            return self._optimizer_result_delete_response(request, common), False

        if request.type == "optimizer_heatmap":
            return self._optimizer_heatmap_response(request, common), False

        if request.type == "shutdown":
            self._log(
                "INFO",
                "Python Engine",
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
                        f"Unsupported Task 012 message type: {request.type}"
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
            # Page by transport size as well as row count. Native MT5 messages
            # can be much longer than application messages; a smaller complete
            # page keeps the next sequence cursor usable without data loss.
            while len(result['events'])>1 and len(Envelope.response('journal_query_ack',request.request_id,payload).to_json().encode('utf-8'))>=MAX_LINE_BYTES-1024:
                result['events']=result['events'][:max(1,len(result['events'])//2)]
                result['transport_page_limited']=True
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

    def _backtest_dataset_inspect_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            path = request.payload.get("path")
            if not isinstance(path, str) or not path.strip():
                raise BacktestError("path is required")

            dataset = load_historical_dataset(path)
            info = dataset.inspect_payload()
            self._log(
                "INFO",
                "Python Engine",
                "BACKTEST_DATASET",
                f"Backtest dataset inspected: {dataset.path.name}",
                details=info,
                correlation_id=request.request_id,
                symbol=dataset.metadata.symbol,
            )
            payload = {
                **common,
                "ok": True,
                "dataset": info,
            }
        except (BacktestError, OSError, ValueError) as exc:
            self._log(
                "WARN",
                "Python Engine",
                "BACKTEST_DATASET",
                f"Backtest dataset rejected: {exc}",
                details={"path": request.payload.get("path")},
                correlation_id=request.request_id,
            )
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }

        return Envelope.response(
            "backtest_dataset_inspect_ack",
            request.request_id,
            payload,
        )

    def _backtest_job_response(self, request: Envelope, common: dict[str, Any]) -> Envelope:
        try:
            if request.type == "backtest_start":
                job = self.backtest_jobs.start(self.active_profile, request.payload)
            elif request.type == "backtest_cancel":
                job = self.backtest_jobs.cancel(str(request.payload.get("job_id", "")))
            else:
                job = self.backtest_jobs.status(str(request.payload.get("job_id", "")))
            payload = {**common, "ok": True, "job": job}
        except (BacktestError, TypeError, ValueError) as error:
            payload = {**common, "ok": False, "errors": [str(error)]}
        return Envelope.response(request.type + "_ack", request.request_id, payload)

    async def _legacy_backtest_async(self, request: Envelope) -> Envelope:
        # Compatibility for CLI clients; the desktop uses start/status/cancel,
        # leaving its heartbeat socket available throughout the job.
        try:
            job = self.backtest_jobs.start(self.active_profile, request.payload)
            while job["state"] in {"QUEUED", "RUNNING", "CANCELLING"}:
                await asyncio.sleep(.025)
                job = self.backtest_jobs.status(job["job_id"])
            if job["state"] != "COMPLETED":
                raise BacktestError("; ".join(job["errors"]) or job["state"])
            stored = await asyncio.to_thread(self.backtests.get, job["run_id"])
            payload = {**self._common(), "ok": True, "result": self._public_backtest_result(stored, trade_offset=0, trade_limit=100)}
        except (BacktestError, TypeError, ValueError) as error:
            payload = {**self._common(), "ok": False, "errors": [str(error)]}
        return Envelope.response("backtest_run_ack", request.request_id, payload)

    def _backtest_history_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            limit = int(request.payload.get("limit", 50))
            history = self.backtests.history(limit=limit)
            payload = {
                **common,
                "ok": True,
                "history": history,
            }
        except (BacktestError, TypeError, ValueError) as exc:
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }

        return Envelope.response(
            "backtest_history_query_ack",
            request.request_id,
            payload,
        )

    def _backtest_result_get_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            run_id = request.payload.get("run_id")
            if not isinstance(run_id, str) or not run_id.strip():
                raise BacktestError("run_id is required")

            offset = int(request.payload.get("trade_offset", 0))
            limit = int(request.payload.get("trade_limit", 100))
            if offset < 0:
                raise BacktestError("trade_offset must be >= 0")
            if not 1 <= limit <= 500:
                raise BacktestError("trade_limit must be 1..500")

            result = self.backtests.get(run_id)
            payload = {
                **common,
                "ok": True,
                "result": self._public_backtest_result(
                    result,
                    trade_offset=offset,
                    trade_limit=limit,
                ),
            }
        except (BacktestError, OSError, TypeError, ValueError) as exc:
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }

        return Envelope.response(
            "backtest_result_get_ack",
            request.request_id,
            payload,
        )

    def _backtest_result_delete_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            run_id = request.payload.get("run_id")
            if not isinstance(run_id, str) or not run_id.strip():
                raise BacktestError("run_id is required")
            deleted = self.backtests.delete(run_id)
            payload = {
                **common,
                "ok": True,
                "deleted": deleted,
                "run_id": run_id,
            }
        except (BacktestError, OSError, TypeError, ValueError) as exc:
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }

        return Envelope.response(
            "backtest_result_delete_ack",
            request.request_id,
            payload,
        )

    @staticmethod
    def _public_backtest_result(
        result: dict[str, Any],
        *,
        trade_offset: int,
        trade_limit: int,
    ) -> dict[str, Any]:
        trades = result.get("trades")
        if not isinstance(trades, list):
            trades = []
        public = {
            key: deepcopy(value)
            for key, value in result.items()
            if key != "trades"
        }
        public["trade_total"] = len(trades)
        public["trade_offset"] = trade_offset
        public["trade_limit"] = trade_limit
        public["trades"] = deepcopy(
            trades[trade_offset : trade_offset + trade_limit]
        )
        return public

    def _optimizer_start_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            start = self.optimizer_jobs.start_research if request.type=='research_start' else self.optimizer_jobs.start_sweep
            status = start(
                dict(request.payload),
                deepcopy(self.active_profile),
            )
            payload = {
                **common,
                "ok": True,
                "status": status,
            }
        except (OptimizerError, BacktestError, OSError, TypeError, ValueError) as exc:
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }
        return Envelope.response(
            request.type + "_ack",
            request.request_id,
            payload,
        )

    def _walk_forward_start_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            status = self.optimizer_jobs.start_walk_forward(
                dict(request.payload),
                deepcopy(self.active_profile),
            )
            payload = {
                **common,
                "ok": True,
                "status": status,
            }
        except (OptimizerError, BacktestError, OSError, TypeError, ValueError) as exc:
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }
        return Envelope.response(
            "walk_forward_start_ack",
            request.request_id,
            payload,
        )

    def _optimizer_status_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            job_id = request.payload.get("job_id")
            if job_id is not None and not isinstance(job_id, str):
                raise OptimizerError("job_id must be string or null")
            status = self.optimizer_jobs.status(job_id)
            payload = {
                **common,
                "ok": True,
                "status": status,
            }
        except (OptimizerError, TypeError, ValueError) as exc:
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }
        return Envelope.response(
            "optimizer_status_ack",
            request.request_id,
            payload,
        )

    def _optimizer_cancel_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            job_id = request.payload.get("job_id")
            if not isinstance(job_id, str) or not job_id.strip():
                raise OptimizerError("job_id is required")
            status = self.optimizer_jobs.cancel(job_id)
            payload = {
                **common,
                "ok": True,
                "status": status,
            }
        except (OptimizerError, TypeError, ValueError) as exc:
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }
        return Envelope.response(
            "optimizer_cancel_ack",
            request.request_id,
            payload,
        )

    def _optimizer_result_get_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            run_id = request.payload.get("run_id")
            if not isinstance(run_id, str) or not run_id.strip():
                raise OptimizerError("run_id is required")
            offset = int(request.payload.get("candidate_offset", 0))
            limit = int(request.payload.get("candidate_limit", 100))
            if offset < 0:
                raise OptimizerError("candidate_offset must be >= 0")
            if not 1 <= limit <= 500:
                raise OptimizerError("candidate_limit must be 1..500")

            result = self.optimizers.get(run_id)
            public = self._public_optimizer_result(
                result,
                candidate_offset=offset,
                candidate_limit=limit,
            )
            payload = {
                **common,
                "ok": True,
                "result": public,
            }
        except (OptimizerError, OSError, TypeError, ValueError) as exc:
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }
        return Envelope.response(
            "optimizer_result_get_ack",
            request.request_id,
            payload,
        )

    def _optimizer_history_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            limit = int(request.payload.get("limit", 50))
            payload = {
                **common,
                "ok": True,
                "history": self.optimizers.history(limit=limit),
            }
        except (OptimizerError, TypeError, ValueError) as exc:
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }
        return Envelope.response(
            "optimizer_history_query_ack",
            request.request_id,
            payload,
        )

    def _optimizer_result_delete_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            run_id = request.payload.get("run_id")
            if not isinstance(run_id, str) or not run_id.strip():
                raise OptimizerError("run_id is required")
            payload = {
                **common,
                "ok": True,
                "deleted": self.optimizers.delete(run_id),
                "run_id": run_id,
            }
        except (OptimizerError, OSError, TypeError, ValueError) as exc:
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }
        return Envelope.response(
            "optimizer_result_delete_ack",
            request.request_id,
            payload,
        )

    def _optimizer_heatmap_response(
        self,
        request: Envelope,
        common: dict[str, Any],
    ) -> Envelope:
        try:
            run_id = request.payload.get("run_id")
            x_path = request.payload.get("x_path")
            y_path = request.payload.get("y_path")
            metric = request.payload.get("metric", "net_profit")
            if not isinstance(run_id, str) or not run_id.strip():
                raise OptimizerError("run_id is required")
            if not isinstance(x_path, str) or not x_path.strip():
                raise OptimizerError("x_path is required")
            if not isinstance(y_path, str) or not y_path.strip():
                raise OptimizerError("y_path is required")
            if not isinstance(metric, str):
                raise OptimizerError("metric must be string")

            result = self.optimizers.get(run_id)
            heatmap = heatmap_from_result(
                result,
                x_path=x_path,
                y_path=y_path,
                metric=metric,
            )
            payload = {
                **common,
                "ok": True,
                "heatmap": heatmap,
            }
        except (OptimizerError, OSError, TypeError, ValueError) as exc:
            payload = {
                **common,
                "ok": False,
                "errors": [str(exc)],
            }
        return Envelope.response(
            "optimizer_heatmap_ack",
            request.request_id,
            payload,
        )

    @staticmethod
    def _public_optimizer_result(
        result: dict[str, Any],
        *,
        candidate_offset: int,
        candidate_limit: int,
    ) -> dict[str, Any]:
        public = {
            key: deepcopy(value)
            for key, value in result.items()
            if key != "candidates"
        }
        candidates = result.get("candidates")
        if isinstance(candidates, list):
            public["candidate_total"] = len(candidates)
            public["candidate_offset"] = candidate_offset
            public["candidate_limit"] = candidate_limit
            public["candidates"] = deepcopy(
                candidates[
                    candidate_offset : candidate_offset + candidate_limit
                ]
            )
        else:
            public["candidate_total"] = 0
            public["candidate_offset"] = 0
            public["candidate_limit"] = candidate_limit
            public["candidates"] = []
        return public

    def _optimizer_journal(
        self,
        tag: str,
        message: str,
        details: dict[str, Any],
    ) -> None:
        level = (
            "ERROR"
            if tag.endswith("_FAILED")
            else "WARN"
            if tag.endswith("_CANCELLED")
            else "INFO"
        )
        self._log(
            level,
            "Python Engine",
            tag,
            message,
            details=details,
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

    def _csv_logging_enabled(self) -> bool:
        try:
            return bool(
                get_path(
                    self.active_profile,
                    "logging.csv_enabled",
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
                mirror_csv=self._csv_logging_enabled(),
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

    def _maintenance_response(self, request: Envelope, common: dict[str, Any]) -> Envelope:
        try:
            extra: dict[str, Any] = {}
            if request.type == "diagnostics_get":
                extra["diagnostics"] = collect_diagnostics(self)
            elif request.type == 'history_catalog':
                extra['datasets'] = self.library.history_catalog()
            elif request.type == 'library_profile_list':
                extra['profiles'] = self.library.profile_list()
            elif request.type == 'library_profile_save':
                extra['saved'] = self.library.save_profile(request.payload.get('id'),request.payload.get('profile'))
            elif request.type == 'startup_profile_set':
                extra['saved'] = self.library.save_startup_profile(request.payload.get('profile'))
            elif request.type == 'startup_profile_clear':
                extra['saved'] = self.library.clear_startup_profile()
            elif request.type == 'data_transfer_start':
                extra['transfer']=self.data_transfer.start(request.payload.get('mode'),request.payload.get('path'))
            elif request.type == 'data_transfer_status':
                extra['transfer']=self.data_transfer.status()
            elif request.type == 'data_transfer_cancel':
                extra['transfer']=self.data_transfer.cancel()
            elif request.type == 'optimizer_candidate_prepare':
                from .optimizer import prepare_candidate
                extra['candidate']=prepare_candidate(self.optimizers.get(request.payload.get('run_id')),
                    self.active_profile,request.payload.get('index'))
            elif request.type == 'library_profile_get':
                extra['profile'] = self.library.profile_get(request.payload.get('id'),request.payload.get('revision'))
            elif request.type == 'calendar_get':
                extra['calendar'] = self.library.calendar
            elif request.type == 'calendar_validate':
                extra['calendar'] = self.library.validate_calendar(request.payload.get('calendar'))
            elif request.type == 'calendar_import':
                extra['calendar'] = self.library.save_calendar(request.payload.get('calendar'))
                self._log('INFO','Alerts','NEWS','User calendar imported',details=extra['calendar'])
            elif request.type.startswith('broker_history_'):
                snapshot = self.bridge.latest_fresh_snapshot() or {}
                identity = {key: snapshot.get(key) for key in ('account_login','account_server','magic')}
                if request.type == 'broker_history_start':
                    terminal = self.settings_store.settings['connection']['mt5_path']
                    if not terminal:
                        terminal = str(Path(snapshot.get('terminal_path',''))/'terminal64.exe') if snapshot.get('terminal_path') else ''
                    extra['history'] = self.broker_history_jobs.start(terminal, identity)
                elif request.type == 'broker_history_status':
                    extra['history'] = self.broker_history_jobs.status()
                else:
                    extra['history'] = self.broker_history_jobs.query(identity, report_id=request.payload.get('report_id'),
                        page=request.payload.get('page',0),limit=request.payload.get('limit',100),symbol=request.payload.get('symbol'))
            elif request.type == "history_download_start":
                snapshot=self.bridge.latest_fresh_snapshot() or {}
                context={'reference_as_of':snapshot.get('server_time'),
                    'assumption':'Current broker UTC offset and Friday schedule held constant; historical DST/session changes must be reviewed'}
                if 'server_utc_offset_seconds' in snapshot:context['server_utc_offset_seconds']=snapshot['server_utc_offset_seconds']
                if snapshot.get('weekend_session_end'):context['friday_session_end_seconds']=snapshot['weekend_session_end']%86400 or 86400
                extra["history_download"] = self.history_jobs.start(
                    request.payload.get("terminal", ""), request.payload.get("symbol", "XAUUSD"),
                    model=request.payload.get('model','M1_OHLC'),from_date=request.payload.get('from_date',''),
                    to_date=request.payload.get('to_date',''),context=context)
            elif request.type == "history_download_status":
                extra["history_download"] = self.history_jobs.status()
            elif request.type == "settings_defaults_get":
                extra["settings"] = default_settings()
            else:
                if request.type == "settings_set":
                    settings = request.payload.get("settings")
                    if not isinstance(settings, dict):
                        raise ValueError("settings must be an object")
                    profile = deepcopy(self.active_profile)
                    if settings.get('safety',{}).get('allow_real_account') != self.settings_store.settings['safety']['allow_real_account']:
                        allow_real = settings['safety']['allow_real_account']
                        profile['execution'].update(allow_real_account=allow_real, demo_only=not allow_real)
                    self.settings_store.save(settings=settings, profile=profile)
                    if profile != self.active_profile:
                        self.active_profile = profile
                        self.strategy.set_profile(profile)
                    self.execution.settings = self.settings_store.settings
                    self._log("INFO", "Python Engine", "SETTINGS", "System settings persisted")
                elif request.type == "backup_create":
                    extra["backup"] = self.settings_store.create_backup()
                    self._log("INFO", "Python Engine", "BACKUP", "Local settings/profile backup created", details=extra["backup"])
                elif request.type == "backup_restore":
                    self.settings_store.restore_backup(request.payload.get("backup_id"))
                    self.active_profile = deepcopy(self.settings_store.profile)
                    self.strategy.set_profile(self.active_profile)
                    self.strategy.reset_setup("BACKUP_RESTORED")
                    self.execution.settings = self.settings_store.settings
                    self._log("WARN", "Python Engine", "RECOVERY", "Backup restored; strategy reset; execution permissions rechecked against restored settings")
                extra.update(self.settings_store.payload())
            return Envelope.response(request.type + "_ack", request.request_id, {**common, "ok": True, **extra})
        except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
            return Envelope.response(request.type + "_ack", request.request_id,
                                     {**common, "ok": False, "errors": [str(exc)]})

    @staticmethod
    async def _write(
        writer: asyncio.StreamWriter,
        envelope: Envelope,
    ) -> None:
        writer.write((envelope.to_json() + "\n").encode("utf-8"))
        await writer.drain()
