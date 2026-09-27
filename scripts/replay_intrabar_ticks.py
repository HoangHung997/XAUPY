"""Replay an archived MT5 tick stream in memory, with no broker/client writes.

CSV bars warm up only when closed by the event timestamp. This validates the
observed-tick strategy; it does not claim uninterrupted live capture or P/L.
"""
from __future__ import annotations

import argparse
from collections import deque
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from xaupy_engine.config_schema import default_profile
from xaupy_engine.strategy_engine import Bar, HISTORY_TIMEFRAME_SECONDS, StrategyEngine


def replay(history_dir: Path, tick_path: Path, profile: dict | None = None) -> dict:
    selected = deepcopy(profile if profile is not None else default_profile())
    selected["trigger"]["confirm_closed_bar"] = False  # In-memory research copy only.
    packets = [json.loads(line) for line in tick_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    event_times = [tick["time_msc"] for packet in packets for tick in packet["tick_batch"]["ticks"]]
    if not event_times or any(b < a for a, b in zip(event_times, event_times[1:])):
        raise ValueError("Archive must contain chronologically ordered tick observations")
    start, end = event_times[0], event_times[-1]
    engine = StrategyEngine(selected)
    schedule: dict[int, dict[str, dict]] = {}
    history_summary = {}
    for tf, seconds in HISTORY_TIMEFRAME_SECONDS.items():
        path = history_dir / f"{selected['strategy']['symbol']}_{tf}.csv"
        seed: deque[Bar] = deque(maxlen=engine.max_history)
        count, previous = 0, None
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                bar = Bar.from_payload(row)
                if previous is not None and bar.time <= previous:
                    raise ValueError(f"{path.name}: bar times must increase")
                previous = bar.time
                closed_at = (bar.time + seconds) * 1000
                if closed_at <= start:
                    seed.append(bar)
                elif closed_at <= end:
                    schedule.setdefault(closed_at, {})[tf] = vars(bar).copy()
                count += 1
        engine.history[tf] = list(seed)
        history_summary[tf] = {"source": str(path), "source_rows": count, "seed_closed_bars": len(seed)}
    engine.reset_setup("ARCHIVED_OBSERVED_TICKS_REPLAY")
    closing_times = sorted(schedule)
    closing_index = 0
    observed_sequence = 0
    previous_archive_stream = None
    previous_archive_sequence = None
    last_signal_sequence = 0
    signals = []
    states: dict[str, int] = {}
    incomplete_packets = 0
    started = time.perf_counter()
    for packet in packets:
        original = packet["tick_batch"]
        stream_id, archive_sequence = original["stream_id"], original["sequence"]
        archive_gap = (previous_archive_stream == stream_id and previous_archive_sequence is not None
                       and archive_sequence != previous_archive_sequence + 1)
        complete = original["complete"] and not archive_gap and previous_archive_stream == stream_id
        if not complete:
            incomplete_packets += 1
        for tick in original["ticks"]:
            while closing_index < len(closing_times) and closing_times[closing_index] <= tick["time_msc"]:
                engine.ingest_snapshot({"symbol": selected["strategy"]["symbol"],
                                        "bars": schedule[closing_times[closing_index]]})
                closing_index += 1
            observed_sequence += 1
            result = engine.ingest_tick_batch({
                "symbol": packet["symbol"], "server_time": tick["time_msc"] // 1000,
                "tick_batch": {"stream_id": stream_id, "sequence": observed_sequence,
                               "complete": complete, "ticks": [tick]},
            })
            states[result["state"]] = states.get(result["state"], 0) + 1
            if result["signal_sequence"] > last_signal_sequence:
                signals.append(deepcopy(result["last_signal"]))
                last_signal_sequence = result["signal_sequence"]
        previous_archive_stream, previous_archive_sequence = stream_id, archive_sequence
    final = engine.status_payload(market_connected=True)
    return {
        "mode": "ARCHIVED_OBSERVED_TICKS_NEXT_BAR", "read_only": True,
        "live_continuity_claimed": False, "profitability_measured": False,
        "broker_execution_requested": False, "active_profile_modified": False,
        "tick_source": str(tick_path), "tick_source_sha256": hashlib.sha256(tick_path.read_bytes()).hexdigest(),
        "ticks": len(event_times), "first_time_msc": start, "last_time_msc": end,
        "original_packets": len(packets), "incomplete_or_gapped_packets": incomplete_packets,
        "replay_note": "Packets split only at observations to publish newly closed bars before each tick; original same-millisecond order retained.",
        "history": history_summary, "profile": selected, "profile_hash": engine.profile_hash,
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "states": states, "signals": signals, "final_strategy": final,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--history-dir", type=Path, required=True)
    parser.add_argument("--ticks", type=Path, required=True)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    input_profile = json.loads(args.profile.read_text(encoding="utf-8-sig")) if args.profile else None
    evidence = replay(args.history_dir, args.ticks, input_profile)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ticks": evidence["ticks"], "signals": len(evidence["signals"]),
                      "states": evidence["states"], "seconds": evidence["elapsed_seconds"], "output": str(args.out)}))
