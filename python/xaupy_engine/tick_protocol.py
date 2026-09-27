"""Bounded tick transport validation; never infer tick paths from candle extrema."""
from __future__ import annotations
import math
from datetime import datetime, timezone
import time
from typing import Any


class TickTransport:
    """Counters for validated, fresh, matching-symbol frames, including retries.

    Independent of signal mode: a closed-bar profile still exposes real EA traffic.
    No raw ticks or unbounded stream/sequence history are retained here.
    """
    def __init__(self) -> None:
        self.summary: dict[str, Any] = {
            "received_batches": 0, "accepted_batches": 0, "received_ticks": 0,
            "last_stream_id": None, "last_sequence": None, "last_complete": None,
            "last_gap_reason": None, "last_received_utc": None,
        }
        self.last_received_monotonic: float | None = None

    def record_accepted(self, payload: dict[str, Any]) -> None:
        batch = payload["tick_batch"]
        self.summary["received_batches"] += 1
        self.summary["accepted_batches"] += 1
        self.summary["received_ticks"] += len(batch["ticks"])
        reason = batch.get("gap_reason")
        self.summary.update(last_stream_id=batch["stream_id"], last_sequence=batch["sequence"],
                            last_complete=batch["complete"],
                            last_gap_reason=reason[:128] if isinstance(reason, str) else None,
                            last_received_utc=datetime.now(timezone.utc).isoformat())
        self.last_received_monotonic = time.monotonic()

    def payload(self) -> dict[str, Any]:
        age = None if self.last_received_monotonic is None else int(max(0, time.monotonic() - self.last_received_monotonic) * 1000)
        return {**self.summary, "age_ms": age}


def validate_tick_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("symbol"), str) or not payload["symbol"]:
        raise ValueError("Tick symbol is required")
    server_time = payload.get("server_time")
    if type(server_time) is not int or server_time <= 0:
        raise ValueError("Tick server_time must be a positive integer")
    batch = payload.get("tick_batch")
    if not isinstance(batch, dict):
        raise ValueError("tick_batch must be an object")
    stream = batch.get("stream_id")
    if not isinstance(stream, str) or not stream or len(stream) > 128:
        raise ValueError("Invalid tick stream_id")
    if type(batch.get("sequence")) is not int or batch["sequence"] < 1 or type(batch.get("complete")) is not bool:
        raise ValueError("Invalid tick sequence or continuity flag")
    ticks = batch.get("ticks")
    if not isinstance(ticks, list) or len(ticks) > 1000:
        raise ValueError("Tick batch must contain at most 1000 ticks")
    previous = 0
    for tick in ticks:
        if not isinstance(tick, dict):
            raise ValueError("Tick must be an object")
        timestamp = tick.get("time_msc")
        if type(timestamp) is not int or timestamp <= 0 or timestamp < previous or timestamp > (server_time + 2) * 1000:
            raise ValueError("Tick timestamps must be chronological and not in the future")
        previous = timestamp
        for field in ("bid", "ask", "last"):
            value = tick.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("Invalid tick price")
        if type(tick.get("flags")) is not int or tick["flags"] < 0:
            raise ValueError("Invalid tick flags")
        if tick["bid"] > 0 and tick["ask"] > 0 and tick["ask"] < tick["bid"]:
            raise ValueError("Tick ask is below bid")
