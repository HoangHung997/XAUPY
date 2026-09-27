"""Observed-tick protocol acceptance with synthetic fixtures in isolated state."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import uuid

from smoke_task014_015_maintenance import engine_session

START = 1_800_000_000
TIMEFRAMES = {"M1": 60, "M3": 180, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H2": 7200, "H4": 14400}


async def exercise_intrabar(request) -> int:
    checks = 0
    def check(value, detail):
        nonlocal checks
        if not value:
            raise AssertionError(detail)
        checks += 1

    profile = (await request("config_active_get"))["profile"]
    profile["strategy"].update(allow_buy=False, allow_sell=True)
    profile["timeframes"] = {role: "M1" for role in ("direction", "pullback", "trigger")}
    profile["direction"]["ma_enabled"] = False
    profile["pullback"].update(rsi_enabled=False, z_enabled=True, z_period=20, z_sell_level=2.5)
    profile["trigger"].update(rsi_enabled=False, z_enabled=True, z_period=20, z_reversal_delta=.3, confirm_closed_bar=False)
    check((await request("config_active_set", {"profile": profile}))["applied"], "isolated intrabar profile applied")
    history = {}
    for tf, seconds in TIMEFRAMES.items():
        anchor = START // seconds * seconds
        history[tf] = [dict(time=anchor - (40 - i) * seconds, open=99 + 2 * (i % 2),
                            high=99 + 2 * (i % 2), low=99 + 2 * (i % 2), close=99 + 2 * (i % 2), tick_volume=10)
                       for i in range(40)]
    snapshot = {"bridge_version": "intrabar-test-fixture", "symbol": "XAUUSD", "server_time": START + 120,
                "terminal_connected": True, "account_trade_mode": "DEMO", "bid": 100, "ask": 100.2,
                "guardian": {"execution_locked": True, "execution_ready": False, "reason": "TEST_EXECUTION_LOCKED"},
                "bars": {tf: rows[-1] for tf, rows in history.items()}, "bar_history": history}
    check((await request("bridge_snapshot", snapshot))["accepted"], "closed history bootstrap accepted")
    def ticks(sequence, values, complete=True):
        return {"symbol": "XAUUSD", "server_time": START + 180, "tick_batch": {
            "stream_id": "isolated-synthetic-ticks", "sequence": sequence, "complete": complete,
            "ticks": [dict(time_msc=START * 1000 + offset, bid=price, ask=price + .2, last=0, flags=6)
                      for offset, price in values]}}
    baseline = await request("bridge_ticks", ticks(1, [(1000, 100)], complete=False))
    check(baseline["accepted"] and baseline["strategy"]["armed_side"] is None, "baseline packet cannot arm")
    armed = await request("bridge_ticks", ticks(2, [(10_000, 120), (50_000, 104)]))
    check(armed["strategy"]["state"] == "ARMED_SELL", "observed intrabar peak survives retreat")
    check(armed["strategy"]["signal_sequence"] == 0, "same candle cannot confirm")
    check(armed["strategy"]["intrabar"]["setup_extremes"]["z"] > 2.5, "peak projected in receipt")
    snapshot.pop("bar_history")
    snapshot["bars"]["M1"] = dict(time=START, open=100, high=120, low=100, close=104, tick_volume=20)
    await request("bridge_snapshot", snapshot)
    confirmation = ticks(3, [(61_000, 103)])
    triggered = await request("bridge_ticks", confirmation)
    check(triggered["strategy"]["state"] == "TRIGGERED_SELL", "following candle reversal confirms")
    check(triggered["strategy"]["last_signal"]["tick_time_msc"] == START * 1000 + 61_000, "signal includes actual observation time")
    repeated = await request("bridge_ticks", confirmation)
    check(repeated["strategy"] == triggered["strategy"], "retried tick sequence is idempotent")
    heartbeat = await request("heartbeat")
    check(heartbeat["strategy"]["signal_sequence"] == 1, "heartbeat carries tick strategy state")
    invalid = ticks(4, [(62_000, 103)])
    invalid["tick_batch"]["ticks"][0]["time_msc"] = (START + 1000) * 1000
    await request("bridge_ticks", invalid, expected="error")
    after_invalid = await request("heartbeat")
    check(after_invalid["strategy"]["signal_sequence"] == 1, "invalid future tick cannot create signal")
    snapshot["terminal_connected"] = False
    await request("bridge_snapshot", snapshot)
    stale = await request("bridge_ticks", ticks(4, [(62_000, 120)]))
    check(not stale["accepted"] and stale["strategy"]["armed_side"] is None, "disconnected market rejects observed ticks")
    snapshot["terminal_connected"] = True
    await request("bridge_snapshot", snapshot)
    reconnected = await request("bridge_ticks", ticks(4, [(63_000, 120)]))
    check(reconnected["accepted"] and reconnected["strategy"]["armed_side"] is None, "same-stream reconnect establishes baseline only")
    await request("bridge_ticks", ticks(5, [(64_000, 120)]))
    gapped = await request("bridge_ticks", ticks(7, [(65_000, 103)]))
    check(gapped["strategy"]["armed_side"] is None and gapped["strategy"]["signal_sequence"] == 1,
          "sequence gap discards setup without repeated signal")
    wrong_symbol = ticks(8, [(66_000, 103)])
    wrong_symbol["symbol"] = "EURUSD"
    check(not (await request("bridge_ticks", wrong_symbol))["accepted"], "mismatched tick symbol rejected")
    profile["trigger"]["confirm_closed_bar"] = True
    await request("config_active_set", {"profile": profile})
    legacy = await request("bridge_ticks", ticks(9, [(67_000, 120)]))
    check(legacy["strategy"]["intrabar"]["mode"] == "CLOSED_BAR" and legacy["strategy"]["armed_side"] is None,
          "closed-bar mode does not opt into tick signals")
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine_exe", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="xaupy-intrabar-smoke-") as temporary:
        with engine_session(str(args.engine_exe.resolve()), Path(temporary)) as stream:
            async def request(kind, payload=None, expected=None):
                identifier = str(uuid.uuid4())
                envelope = {"schema_version": 1, "type": kind, "request_id": identifier,
                            "sent_at_utc": datetime.now(timezone.utc).isoformat(), "payload": payload or {}}
                stream.write((json.dumps(envelope) + "\n").encode()); stream.flush()
                reply = json.loads(stream.readline(1024 * 1024 + 1))
                assert reply["request_id"] == identifier
                expected = expected or ("config_active_ack" if kind == "config_active_get" else kind + "_ack")
                assert reply["type"] == expected, reply
                data = reply["payload"]
                assert data["trading_enabled"] is False and data["execution_enabled"] is False
                assert data.get("command") is None
                return data
            checks = asyncio.run(exercise_intrabar(request))
            print(f"Packaged intrabar acceptance: {checks} checks passed; isolated synthetic fixture, broker execution locked.")


if __name__ == "__main__":
    main()
