"""Read-only end-to-end Bridge acceptance; never sends trade or config commands."""
from __future__ import annotations
import argparse
import json
import math
import socket
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

MAX_FRAME_BYTES = 1024 * 1024
REQUIRED_TIMEFRAMES = {"M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4"}


def assess_samples(samples: list[dict]) -> dict[str, bool]:
    """Check transport/projection evidence without requiring an open market."""
    if len(samples) < 2:
        return {"multiple_samples": False}
    final = samples[-1]
    totals = [sample["bridge"].get("snapshots_total") for sample in samples]
    elapsed = [sample.get("elapsed_ms") for sample in samples]
    ticks = [sample.get("tick_time_msc") for sample in samples]
    history = final.get("history_counts") or {}
    seen = final.get("bars_seen") or {}
    integer_totals = all(type(value) is int and value >= 0 for value in totals)
    valid_elapsed = all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in elapsed)
    valid_ticks = all(type(value) is int and value > 0 for value in ticks)
    complete_history = REQUIRED_TIMEFRAMES.issubset(history) and all(
        type(history[tf]) is int and 0 < history[tf] <= 256 for tf in REQUIRED_TIMEFRAMES
    )
    return {
        "multiple_samples": True,
        "sample_clock_monotonic": valid_elapsed and all(b > a for a, b in zip(elapsed, elapsed[1:])),
        "bridge_connected": all(s["bridge"].get("connected") is True for s in samples),
        "terminal_connected": all(s["bridge"].get("terminal_connected") is True for s in samples),
        "demo_account": all(s["bridge"].get("account_trade_mode") == "DEMO" for s in samples),
        "execution_locked": all(
            s["bridge"].get("execution_locked") is True
            and s["bridge"].get("execution_ready") is False
            and s.get("trading_enabled") is False
            and s.get("execution_enabled") is False
            and s.get("strategy_trading_enabled") is False
            and s.get("strategy_execution_enabled") is False for s in samples
        ),
        "snapshot_fresh": all(type(s["bridge"].get("age_ms")) is int and 0 <= s["bridge"]["age_ms"] < 5000 for s in samples),
        "overview_available": all(s.get("overview_available") is True for s in samples),
        "snapshot_counter_monotonic": integer_totals and all(b >= a for a, b in zip(totals, totals[1:])),
        "new_snapshots_received": integer_totals and totals[-1] > totals[0],
        "quote_valid": all(
            type(s.get("bid")) in (int, float) and type(s.get("ask")) in (int, float)
            and math.isfinite(s["bid"]) and math.isfinite(s["ask"])
            and 0 < s["bid"] <= s["ask"] for s in samples
        ),
        "history_available": complete_history,
        "strategy_history_loaded": complete_history and REQUIRED_TIMEFRAMES.issubset(seen) and all(
            type(seen[tf]) is int and seen[tf] >= history[tf] for tf in REQUIRED_TIMEFRAMES
        ),
        "strategy_ready": final.get("strategy_ready") is True,
        "tick_timestamp_available": valid_ticks,
        "tick_time_nondecreasing": valid_ticks and all(b >= a for a, b in zip(ticks, ticks[1:])),
    }


def probe(port: int, duration: float) -> dict:
    if not math.isfinite(duration) or not 1 <= duration <= 300:
        raise ValueError("duration must be 1..300 seconds")
    if not 1 <= port <= 65535:
        raise ValueError("port must be 1..65535")
    samples = []
    with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
        stream = connection.makefile("rwb")
        def request(kind):
            if kind not in {"hello", "heartbeat"}:
                raise ValueError("Acceptance probe permits read-only hello/heartbeat only")
            identifier = str(uuid.uuid4())
            envelope = {"schema_version": 1, "type": kind, "request_id": identifier,
                        "sent_at_utc": datetime.now(timezone.utc).isoformat(),
                        "payload": {"component": "desktop", "desktop_version": "acceptance-probe"}}
            stream.write((json.dumps(envelope) + "\n").encode())
            stream.flush()
            frame = stream.readline(MAX_FRAME_BYTES + 1)
            if not frame.endswith(b"\n") or len(frame) > MAX_FRAME_BYTES:
                raise RuntimeError("IPC response is incomplete or exceeds frame limit")
            reply = json.loads(frame)
            if reply.get("request_id") != identifier or reply.get("type") != kind + "_ack" or reply.get("schema_version") != 1:
                raise RuntimeError("IPC response schema/type/correlation failed")
            payload = reply["payload"]
            if payload.get("trading_enabled") is not False or payload.get("execution_enabled") is not False:
                raise RuntimeError("Engine reports an unlocked execution state")
            return payload
        hello = request("hello")
        started = time.monotonic()
        deadline = started + duration
        while True:
            payload = request("heartbeat")
            bridge = payload.get("bridge", {})
            overview = payload.get("overview", {})
            strategy = payload.get("strategy", {})
            samples.append({"utc": datetime.now(timezone.utc).isoformat(),
                            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                            "bridge": bridge, "overview_available": overview.get("available"),
                            "snapshot_received_utc": overview.get("snapshot_received_utc"),
                            "bid": overview.get("bid"), "ask": overview.get("ask"),
                            "tick_time_msc": overview.get("tick_time_msc"),
                            "trading_enabled": payload.get("trading_enabled"),
                            "execution_enabled": payload.get("execution_enabled"),
                            "strategy_trading_enabled": strategy.get("trading_enabled"),
                            "strategy_execution_enabled": strategy.get("execution_enabled"),
                            "history_counts": {tf: len(bars) for tf, bars in overview.get("bar_history", {}).items()},
                            "strategy_state": strategy.get("state"),
                            "strategy_ready": strategy.get("ready"),
                            "bars_seen": strategy.get("bars_seen")})
            if time.monotonic() >= deadline:
                break
            time.sleep(1)
        stream.close()
    checks = assess_samples(samples)
    return {"passed": all(checks.values()), "checks": checks,
            "scope": "EA-to-Python (Avalonia requires separate evidence)", "read_only": True,
            "requests_sent": ["hello", "heartbeat"],
            "price_freshness_policy": "Unchanged last-session ticks are valid; transport freshness does not imply an open market.",
            "engine_version": hello.get("engine_version"),
            "duration_seconds": duration, "samples": samples}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=39421)
    parser.add_argument("--duration", type=float, default=10)
    parser.add_argument("--out", type=Path, default=Path("artifacts/live-bridge-evidence.json"))
    args = parser.parse_args()
    result = probe(args.port, args.duration)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "samples": len(result["samples"]), "output": str(args.out)}))
    raise SystemExit(0 if result["passed"] else 1)
