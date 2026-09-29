from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import time
import math
from datetime import datetime, timezone
from typing import Any

from .strategy_engine import Bar, HISTORY_LIMIT, HISTORY_TIMEFRAME_SECONDS, StrategyDataError, validated_bar_history


class BridgeSnapshotError(ValueError):
    """Raised when an MT5 Bridge snapshot violates XAUPY bridge rules."""


@dataclass(frozen=True)
class BridgeStatus:
    connected: bool
    age_ms: int | None
    symbol: str | None
    terminal_connected: bool
    account_trade_mode: str | None
    execution_ready: bool
    execution_locked: bool
    guardian_reason: str
    snapshots_total: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "age_ms": self.age_ms,
            "symbol": self.symbol,
            "terminal_connected": self.terminal_connected,
            "account_trade_mode": self.account_trade_mode,
            "execution_ready": self.execution_ready,
            "execution_locked": self.execution_locked,
            "guardian_reason": self.guardian_reason,
            "snapshots_total": self.snapshots_total,
        }


class BridgeRegistry:
    def __init__(self, stale_seconds: float = 5.0) -> None:
        if stale_seconds <= 0:
            raise ValueError("stale_seconds must be positive")

        self.stale_seconds = stale_seconds
        self._last_seen_monotonic: float | None = None
        self._last_snapshot_monotonic: float | None = None
        self._latest_snapshot: dict[str, Any] | None = None
        self._latest_snapshot_received_utc: str | None = None
        self._latest_hello: dict[str, Any] | None = None
        self._snapshots_total = 0
        self._bar_history: dict[str, list[dict[str, Any]]] = {}
        # Executable prices have their own clock. A tick must never be compared
        # to an older account snapshot's server_time, or keep stale account data
        # alive. All clock advancement is monotonic, not the PC's UTC timezone.
        self._execution_tick: dict[str, Any] | None = None
        self._execution_frame: tuple[int, float] | None = None
        self._execution_stream: str | None = None
        self._execution_sequence = 0
        self._retired_execution_streams: list[str] = []

    def record_hello(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise BridgeSnapshotError("bridge hello payload must be an object")

        bridge_version = payload.get("bridge_version")
        if not isinstance(bridge_version, str) or not bridge_version.strip():
            raise BridgeSnapshotError("bridge_version is required")

        self._latest_hello = dict(payload)
        self._last_seen_monotonic = time.monotonic()

    def record_heartbeat(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise BridgeSnapshotError("bridge heartbeat payload must be an object")
        self._last_seen_monotonic = time.monotonic()

    def record_snapshot(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise BridgeSnapshotError("bridge snapshot payload must be an object")

        required = {
            "symbol",
            "terminal_connected",
            "account_trade_mode",
            "bid",
            "ask",
            "guardian",
            "bars",
        }
        missing = sorted(required.difference(payload))
        if missing:
            raise BridgeSnapshotError(f"bridge snapshot missing fields: {missing}")

        symbol = payload["symbol"]
        if not isinstance(symbol, str) or not symbol.strip():
            raise BridgeSnapshotError("symbol must be a non-empty string")

        if not isinstance(payload["terminal_connected"], bool):
            raise BridgeSnapshotError("terminal_connected must be boolean")
        tick_time = payload.get("tick_time_msc")
        if tick_time is not None and (isinstance(tick_time, bool) or not isinstance(tick_time, int) or tick_time < 0):
            raise BridgeSnapshotError("tick_time_msc must be a nonnegative integer")

        guardian = payload["guardian"]
        if not isinstance(guardian, dict):
            raise BridgeSnapshotError("guardian must be an object")

        if payload.get('execution_capable') is True:
            if (type(guardian.get('execution_locked')) is not bool or type(guardian.get('execution_ready')) is not bool
                    or guardian['execution_locked'] and guardian['execution_ready']):
                raise BridgeSnapshotError('Invalid guardian execution state')
        elif guardian.get('execution_locked') is not True or guardian.get('execution_ready') is not False:
            raise BridgeSnapshotError('Legacy bridge requires locked execution')

        bars = payload["bars"]
        if not isinstance(bars, dict):
            raise BridgeSnapshotError("bars must be an object")

        required_timeframes = {"M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4"}
        missing_timeframes = sorted(required_timeframes.difference(bars))
        if missing_timeframes:
            raise BridgeSnapshotError(
                f"bridge snapshot missing timeframe bars: {missing_timeframes}"
            )
        try:
            validated_history = validated_bar_history(payload)
        except StrategyDataError as exc:
            raise BridgeSnapshotError(str(exc)) from exc

        for collection_name in ("positions", "orders", "deals", "all_positions", "all_deals"):
            collection = payload.get(collection_name, [])
            if not isinstance(collection, list):
                raise BridgeSnapshotError(f"{collection_name} must be an array")
            for index, item in enumerate(collection):
                if not isinstance(item, dict):
                    raise BridgeSnapshotError(
                        f"{collection_name}[{index}] must be an object"
                    )

        snapshot_magic = payload.get("magic")
        if any(name in payload for name in ("all_positions", "all_deals")) and (isinstance(snapshot_magic, bool) or not isinstance(snapshot_magic, int)):
            raise BridgeSnapshotError("all-symbol collections require a valid bridge magic")
        if isinstance(snapshot_magic, int):
            for collection_name in ("positions", "orders", "deals", "all_positions", "all_deals"):
                for index, item in enumerate(payload.get(collection_name, [])):
                    item_magic = item.get("magic")
                    if (collection_name.startswith("all_") or item_magic is not None) and item_magic != snapshot_magic:
                        raise BridgeSnapshotError(
                            f"{collection_name}[{index}] magic does not match bridge magic"
                        )

        positions = payload.get("positions", [])
        orders = payload.get("orders", [])
        positions_count = payload.get("positions_count")
        orders_count = payload.get("orders_count")
        if (
            "positions" in payload
            and isinstance(positions_count, int)
            and positions_count != len(positions)
        ):
            raise BridgeSnapshotError("positions_count does not match positions array")
        if (
            "orders" in payload
            and isinstance(orders_count, int)
            and orders_count != len(orders)
        ):
            raise BridgeSnapshotError("orders_count does not match orders array")

        if self._latest_snapshot and self._latest_snapshot.get("symbol") != symbol:
            self._bar_history.clear()
        # Keep every supported series, including optional D1 from newer EAs.
        # The required set above stays compatible with the older eight-TF bridge.
        for timeframe in HISTORY_TIMEFRAME_SECONDS:
            combined = {item["time"]: item for item in self._bar_history.get(timeframe, [])}
            for bar in validated_history.get(timeframe, []):
                combined[bar.time] = vars(bar).copy()
            raw_latest = bars.get(timeframe)
            if isinstance(raw_latest, dict):
                try:
                    bar = Bar.from_payload(raw_latest)
                    combined[bar.time] = vars(bar).copy()
                except StrategyDataError:
                    pass  # Legacy latest-bar errors remain visible to StrategyEngine.
            self._bar_history[timeframe] = [combined[t] for t in sorted(combined)[-HISTORY_LIMIT:]]
        identity = ("bridge_session_id", "account_login", "account_server", "symbol", "magic")
        if self._latest_snapshot is None or any(
            self._latest_snapshot.get(k) != payload.get(k) for k in identity
        ):
            self._execution_tick = None
            self._execution_frame = None
            self._execution_stream = None
            self._execution_sequence = 0
            self._retired_execution_streams.clear()
        self._latest_snapshot = deepcopy(payload)
        self._latest_snapshot_received_utc = datetime.now(timezone.utc).isoformat()
        now = time.monotonic()
        self._last_seen_monotonic = now
        self._last_snapshot_monotonic = now
        self._snapshots_total += 1

    def overview_payload(self, *, include_history: bool = True) -> dict[str, Any]:
        status = self.status()
        snapshot = self._latest_snapshot or {}

        if not status.connected or not self.snapshot_fresh() or not snapshot:
            return {
                "available": False,
                "snapshot_received_utc": None,
                "symbol": status.symbol,
                "account_trade_mode": status.account_trade_mode,
                "terminal_connected": status.terminal_connected,
                "bid": None,
                "ask": None,
                "tick_time_msc": None,
                "server_time": None,
                "spread_points": None,
                "point": None,
                "balance": None,
                "equity": None,
                "margin_free": None,
                "account_currency": None,
                "positions_count": 0,
                "orders_count": 0,
                "bars": {},
                "bar_history": {},
            }

        bars = snapshot.get("bars")
        if not isinstance(bars, dict):
            bars = {}

        result = {
            "available": True,
            "snapshot_received_utc": self._latest_snapshot_received_utc,
            "symbol": snapshot.get("symbol"),
            "account_trade_mode": snapshot.get("account_trade_mode"),
            "terminal_connected": bool(snapshot.get("terminal_connected", False)),
            "bid": snapshot.get("bid"),
            "ask": snapshot.get("ask"),
            "tick_time_msc": snapshot.get("tick_time_msc") or None,
            "server_time": snapshot.get("server_time") or None,
            "spread_points": snapshot.get("spread_points"),
            "point": snapshot.get("point"),
            "balance": snapshot.get("balance"),
            "equity": snapshot.get("equity"),
            "margin_free": snapshot.get("margin_free"),
            "account_currency": snapshot.get("account_currency"),
            "positions_count": snapshot.get("positions_count", len(snapshot.get("positions", []))),
            "orders_count": snapshot.get("orders_count", len(snapshot.get("orders", []))),
            "bars": deepcopy(bars),
        }
        if include_history:
            result["bar_history"] = deepcopy(self._bar_history)
        return result

    def orders_positions_payload(self) -> dict[str, Any]:
        status = self.status()
        snapshot = self._latest_snapshot or {}

        if not status.connected or not self.snapshot_fresh() or not snapshot:
            return {
                "available": False,
                "snapshot_received_utc": None,
                "symbol": status.symbol,
                "account_trade_mode": status.account_trade_mode,
                "terminal_connected": status.terminal_connected,
                "account_login": None,
                "account_currency": None,
                "leverage": None,
                "bid": None,
                "ask": None,
                "spread_points": None,
                "point": None,
                "balance": None,
                "equity": None,
                "margin_free": None,
                "open_pl": None,
                "realized_pl": None,
                "exposure_lots": 0.0,
                "risk_usd": None,
                "risk_pct": None,
                "risk_complete": False,
                "positions_count": 0,
                "orders_count": 0,
                "positions": [],
                "orders": [],
                "deals": [],
                "volume_min": None,
                "volume_max": None,
                "volume_step": None,
                "tick_size": None,
                "tick_value": None,
                "stops_level": None,
                "freeze_level": None,
                "guardian_reason": status.guardian_reason,
                "broker_execution_locked": True,
                "simulation_only": True,
            }

        positions = deepcopy(snapshot.get("positions", []))
        orders = deepcopy(snapshot.get("orders", []))
        deals = deepcopy(snapshot.get("deals", []))

        open_pl = 0.0
        exposure_lots = 0.0
        risk_usd = 0.0
        risk_complete = True

        tick_size = self._positive_number(snapshot.get("tick_size"))
        tick_value = self._positive_number(snapshot.get("tick_value_loss", snapshot.get("tick_value")))

        for position in positions:
            open_pl += self._number(position.get("profit"))
            open_pl += self._number(position.get("swap"))
            volume = max(0.0, self._number(position.get("volume")))
            exposure_lots += volume

            open_price = self._positive_number(position.get("price_open"))
            sl = self._positive_number(position.get("sl"))
            if (
                volume <= 0
                or open_price is None
                or sl is None
                or tick_size is None
                or tick_value is None
            ):
                risk_complete = False
                continue

            side = position.get("side")
            if side not in {"BUY", "SELL"}:
                risk_complete = False
                continue
            # A stop protecting profit is not a potential loss from entry.
            distance = max(0.0, open_price-sl if side == "BUY" else sl-open_price)
            risk_usd += distance / tick_size * tick_value * volume

        realized_pl_value = snapshot.get("own_daily_realized")
        if not isinstance(realized_pl_value, (int, float)) or isinstance(realized_pl_value, bool):
            realized_pl = sum(self._number(item.get("realized_total")) for item in deals)
        else:
            realized_pl = float(realized_pl_value)

        equity = self._positive_number(snapshot.get("equity"))
        risk_pct = None
        if risk_complete and equity is not None:
            risk_pct = risk_usd / equity * 100.0

        return {
            "available": True,
            "snapshot_received_utc": self._latest_snapshot_received_utc,
            "symbol": snapshot.get("symbol"),
            "account_trade_mode": snapshot.get("account_trade_mode"),
            "terminal_connected": bool(snapshot.get("terminal_connected", False)),
            "account_login": snapshot.get("account_login"),
            "account_currency": snapshot.get("account_currency"),
            "leverage": snapshot.get("leverage"),
            "bid": snapshot.get("bid"),
            "ask": snapshot.get("ask"),
            "spread_points": snapshot.get("spread_points"),
            "point": self._positive_number(snapshot.get("point")),
            "balance": snapshot.get("balance"),
            "equity": snapshot.get("equity"),
            "margin_free": snapshot.get("margin_free"),
            "open_pl": open_pl,
            "realized_pl": realized_pl,
            "exposure_lots": exposure_lots,
            "risk_usd": risk_usd if risk_complete else None,
            "risk_pct": risk_pct,
            "risk_complete": risk_complete,
            "positions_count": len(positions),
            "orders_count": len(orders),
            "positions": deepcopy(snapshot.get("all_positions", positions)),
            "orders": orders,
            "deals": deepcopy(snapshot.get("all_deals", deals)),
            "volume_min": snapshot.get("volume_min"),
            "volume_max": snapshot.get("volume_max"),
            "volume_step": snapshot.get("volume_step"),
            "tick_size": snapshot.get("tick_size"),
            "tick_value": snapshot.get("tick_value"),
            "stops_level": snapshot.get("stops_level"),
            "freeze_level": snapshot.get("freeze_level"),
            "guardian_reason": status.guardian_reason,
            "broker_execution_locked": status.execution_locked,
            "simulation_only": snapshot.get('execution_capable') is not True,
            "account_server": snapshot.get('account_server'),
            "magic": snapshot.get('magic'),
        }

    def latest_fresh_snapshot(self) -> dict[str, Any] | None:
        status = self.status()
        if (
            not status.connected
            or not self.snapshot_fresh()
            or self._latest_snapshot is None
        ):
            return None
        return deepcopy(self._latest_snapshot)

    def record_execution_ticks(self, payload: dict[str, Any], session_id: str | None) -> bool:
        """Accept a quote/clock pair only from the connected owning EA session.

        The transport is validated at the protocol boundary and again here so
        direct callers cannot inject non-finite/future quotes. Duplicate frames
        do not refresh the age. Missing ticks affect strategy continuity, but a
        newest actual quoted tick is still valid for a manual market request.
        """
        from .tick_protocol import validate_tick_payload
        validate_tick_payload(payload)
        snapshot = self._latest_snapshot
        if (not session_id or not snapshot or not self.market_data_connected()
                or session_id != snapshot.get("bridge_session_id")
                or payload["symbol"] != snapshot.get("symbol")):
            return False
        batch = payload["tick_batch"]
        stream, sequence = batch["stream_id"], batch["sequence"]
        if stream in self._retired_execution_streams:
            return False
        if stream == self._execution_stream and sequence <= self._execution_sequence:
            return False
        if stream != self._execution_stream:
            if self._execution_stream is not None:
                self._retired_execution_streams.append(self._execution_stream)
                del self._retired_execution_streams[:-16]
            self._execution_stream = stream
            self._execution_tick = None
        self._execution_sequence = sequence
        now = time.monotonic()
        # Do not move the reference clock backwards on a delayed frame.
        server_ms = payload["server_time"] * 1000
        if self._execution_frame:
            prior_ms, received = self._execution_frame
            server_ms = max(server_ms, prior_ms + int(max(0, now-received)*1000))
        self._execution_frame = (server_ms, now)
        for tick in reversed(batch["ticks"]):
            if tick["bid"] > 0 and tick["ask"] >= tick["bid"]:
                if not self._execution_tick or tick["time_msc"] >= self._execution_tick["time_msc"]:
                    self._execution_tick = {k: tick[k] for k in ("bid", "ask", "time_msc")}
                break
        return True

    def execution_snapshot(self) -> dict[str, Any] | None:
        """Small fresh-account snapshot with coherent newest quote and age.

        The server clock has one-second precision. quote_age_ms may therefore
        be slightly negative within that precision; the caller enforces a
        bounded future tolerance independently of its maximum quote age.
        """
        if not self.market_data_connected() or self._latest_snapshot is None:
            return None
        snapshot = deepcopy({k: v for k, v in self._latest_snapshot.items()
                             if k not in {"bars", "bar_history", "all_positions", "all_deals"}})
        now = time.monotonic()
        age = max(0, now - self._last_snapshot_monotonic)
        server_time = snapshot.get("server_time")
        if type(server_time) is not int or server_time <= 0:
            snapshot.update(quote_age_ms=None, snapshot_age_ms=int(age*1000), quote_source="INVALID_CLOCK")
            return snapshot
        server_ms = server_time * 1000 + int(age * 1000)
        quote_source = "SNAPSHOT"
        if self._execution_frame:
            frame_ms, received = self._execution_frame
            server_ms = max(server_ms, frame_ms + int(max(0, now-received)*1000))
        quote = self._execution_tick
        if quote and quote["time_msc"] >= snapshot.get("tick_time_msc", 0):
            snapshot.update(bid=quote["bid"], ask=quote["ask"], tick_time_msc=quote["time_msc"])
            quote_source = "TICK_BATCH"
        snapshot["server_time"] = server_ms // 1000
        snapshot["execution_clock_msc"] = server_ms
        snapshot["quote_age_ms"] = server_ms - int(snapshot.get("tick_time_msc", 0))
        snapshot["snapshot_age_ms"] = int(age * 1000)
        snapshot["quote_source"] = quote_source
        point = self._positive_number(snapshot.get("point"))
        if point:
            snapshot["spread_points"] = (snapshot["ask"]-snapshot["bid"])/point
        return snapshot

    def snapshot_fresh(self) -> bool:
        if self._last_snapshot_monotonic is None:
            return False
        age = max(0.0, time.monotonic() - self._last_snapshot_monotonic)
        return age <= self.stale_seconds

    def market_data_connected(self) -> bool:
        status = self.status()
        return status.connected and status.terminal_connected and self.snapshot_fresh()

    def status(self) -> BridgeStatus:
        now = time.monotonic()
        age_ms: int | None = None
        connected = False

        if self._last_seen_monotonic is not None:
            age = max(0.0, now - self._last_seen_monotonic)
            age_ms = int(age * 1000)
            connected = age <= self.stale_seconds

        snapshot = self._latest_snapshot or {}
        hello = self._latest_hello or {}
        guardian = snapshot.get("guardian")
        if not isinstance(guardian, dict):
            guardian = {}

        return BridgeStatus(
            connected=connected,
            age_ms=age_ms,
            symbol=snapshot.get("symbol") or hello.get("symbol"),
            terminal_connected=bool(snapshot.get("terminal_connected", False)),
            account_trade_mode=(
                str(snapshot["account_trade_mode"])
                if snapshot.get("account_trade_mode") is not None
                else None
            ),
            execution_ready=connected and snapshot.get('execution_capable') is True and guardian.get('execution_ready') is True,
            execution_locked=not connected or snapshot.get('execution_capable') is not True or guardian.get('execution_locked', True),
            guardian_reason=str(
                guardian.get("reason", "TASK003_EXECUTION_LOCKED")
            ),
            snapshots_total=self._snapshots_total,
        )

    @staticmethod
    def _number(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0.0
        return float(value) if math.isfinite(value) else 0.0

    @staticmethod
    def _positive_number(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
