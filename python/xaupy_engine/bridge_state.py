from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any


class BridgeSnapshotError(ValueError):
    """Raised when an MT5 Bridge snapshot violates Task 003 rules."""


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
            raise BridgeSnapshotError("Task 003 requires guardian.execution_locked=true")

        if guardian.get("execution_ready") is not False:
            raise BridgeSnapshotError("Task 003 requires guardian.execution_ready=false")

        bars = payload["bars"]
        if not isinstance(bars, dict):
            raise BridgeSnapshotError("bars must be an object")

        required_timeframes = {"M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4"}
        missing_timeframes = sorted(required_timeframes.difference(bars))
        if missing_timeframes:
            raise BridgeSnapshotError(
                f"bridge snapshot missing timeframe bars: {missing_timeframes}"
            )

        self._latest_snapshot = dict(payload)
        self._last_seen_monotonic = time.monotonic()
        self._snapshots_total += 1

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
