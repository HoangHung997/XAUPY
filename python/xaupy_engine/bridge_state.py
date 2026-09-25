from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import time
from datetime import datetime, timezone
from typing import Any


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
        self._latest_snapshot: dict[str, Any] | None = None
        self._latest_snapshot_received_utc: str | None = None
        self._latest_hello: dict[str, Any] | None = None
        self._snapshots_total = 0

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

        guardian = payload["guardian"]
        if not isinstance(guardian, dict):
            raise BridgeSnapshotError("guardian must be an object")

        if guardian.get("execution_locked") is not True:
            raise BridgeSnapshotError("Task 009 requires guardian.execution_locked=true")

        if guardian.get("execution_ready") is not False:
            raise BridgeSnapshotError("Task 009 requires guardian.execution_ready=false")

        bars = payload["bars"]
        if not isinstance(bars, dict):
            raise BridgeSnapshotError("bars must be an object")

        required_timeframes = {"M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4"}
        missing_timeframes = sorted(required_timeframes.difference(bars))
        if missing_timeframes:
            raise BridgeSnapshotError(
                f"bridge snapshot missing timeframe bars: {missing_timeframes}"
            )

        for collection_name in ("positions", "orders", "deals"):
            collection = payload.get(collection_name, [])
            if not isinstance(collection, list):
                raise BridgeSnapshotError(f"{collection_name} must be an array")
            for index, item in enumerate(collection):
                if not isinstance(item, dict):
                    raise BridgeSnapshotError(
                        f"{collection_name}[{index}] must be an object"
                    )

        snapshot_magic = payload.get("magic")
        if isinstance(snapshot_magic, int):
            for collection_name in ("positions", "orders", "deals"):
                for index, item in enumerate(payload.get(collection_name, [])):
                    item_magic = item.get("magic")
                    if item_magic is not None and item_magic != snapshot_magic:
                        raise BridgeSnapshotError(
                            f"{collection_name}[{index}] magic does not match bridge magic"
                        )

        positions = payload.get("positions", [])
        orders = payload.get("orders", [])
        positions_count = payload.get("positions_count")
        orders_count = payload.get("orders_count")
        if isinstance(positions_count, int) and positions_count != len(positions):
            raise BridgeSnapshotError("positions_count does not match positions array")
        if isinstance(orders_count, int) and orders_count != len(orders):
            raise BridgeSnapshotError("orders_count does not match orders array")

        self._latest_snapshot = deepcopy(payload)
        self._latest_snapshot_received_utc = datetime.now(timezone.utc).isoformat()
        self._last_seen_monotonic = time.monotonic()
        self._snapshots_total += 1

    def overview_payload(self) -> dict[str, Any]:
        status = self.status()
        snapshot = self._latest_snapshot or {}

        if not status.connected or not snapshot:
            return {
                "available": False,
                "snapshot_received_utc": None,
                "symbol": status.symbol,
                "account_trade_mode": status.account_trade_mode,
                "terminal_connected": status.terminal_connected,
                "bid": None,
                "ask": None,
                "spread_points": None,
                "point": None,
                "balance": None,
                "equity": None,
                "margin_free": None,
                "account_currency": None,
                "positions_count": 0,
                "orders_count": 0,
                "bars": {},
            }

        bars = snapshot.get("bars")
        if not isinstance(bars, dict):
            bars = {}

        return {
            "available": True,
            "snapshot_received_utc": self._latest_snapshot_received_utc,
            "symbol": snapshot.get("symbol"),
            "account_trade_mode": snapshot.get("account_trade_mode"),
            "terminal_connected": bool(snapshot.get("terminal_connected", False)),
            "bid": snapshot.get("bid"),
            "ask": snapshot.get("ask"),
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

    def orders_positions_payload(self) -> dict[str, Any]:
        status = self.status()
        snapshot = self._latest_snapshot or {}

        if not status.connected or not snapshot:
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
        tick_value = self._positive_number(snapshot.get("tick_value"))

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

            risk_usd += abs(open_price - sl) / tick_size * tick_value * volume

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
            "positions": positions,
            "orders": orders,
            "deals": deals,
            "volume_min": snapshot.get("volume_min"),
            "volume_max": snapshot.get("volume_max"),
            "volume_step": snapshot.get("volume_step"),
            "tick_size": snapshot.get("tick_size"),
            "tick_value": snapshot.get("tick_value"),
            "stops_level": snapshot.get("stops_level"),
            "freeze_level": snapshot.get("freeze_level"),
            "guardian_reason": status.guardian_reason,
            "broker_execution_locked": True,
            "simulation_only": True,
        }

    def latest_fresh_snapshot(self) -> dict[str, Any] | None:
        status = self.status()
        if not status.connected or self._latest_snapshot is None:
            return None
        return deepcopy(self._latest_snapshot)

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
            execution_ready=False,
            execution_locked=True,
            guardian_reason=str(
                guardian.get("reason", "TASK003_EXECUTION_LOCKED")
            ),
            snapshots_total=self._snapshots_total,
        )

    @staticmethod
    def _number(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0.0
        return float(value)

    @staticmethod
    def _positive_number(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        number = float(value)
        return number if number > 0 else None
