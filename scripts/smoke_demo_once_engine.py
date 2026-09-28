"""Isolated synthetic EA/strategy/one-shot protocol smoke; no MT5 is connected."""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from uuid import uuid4

from smoke_intrabar_engine import START, TIMEFRAMES
from smoke_task014_015_maintenance import engine_session


async def exercise_demo_once(request) -> int:
    checks = 0
    def check(value, label):
        nonlocal checks
        if not value:
            raise AssertionError(label)
        checks += 1
    session, attempt = str(uuid4()), str(uuid4())
    profile = (await request("config_active_get"))["profile"]
    profile["strategy"].update(allow_buy=False, allow_sell=True)
    profile["timeframes"] = {role: "M1" for role in ("direction", "pullback", "trigger")}
    profile["direction"]["ma_enabled"] = False
    profile["pullback"].update(rsi_enabled=False, z_enabled=True, z_period=20, z_sell_level=2.5)
    profile["trigger"].update(rsi_enabled=False, z_enabled=True, z_period=20,
                               z_reversal_delta=.3, confirm_closed_bar=False)
    profile["stop_loss"].update(mode="FIXED", fixed_price_units=3.0)
    profile["sessions"].update(session1_enabled=False, session2_enabled=False)
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
        profile["sessions"][day] = True
    check((await request("config_active_set", {"profile": profile}))["applied"], "synthetic profile applied")
    await request("bridge_hello", {"bridge_version": "isolated-demo-smoke", "component": "mt5-bridge",
                                   "bridge_session_id": session, "demo_once_capable": True, "symbol": "XAUUSD"})
    history = {}
    for tf, seconds in TIMEFRAMES.items():
        anchor = START // seconds * seconds
        history[tf] = [dict(time=anchor - (40 - i) * seconds, open=99 + 2 * (i % 2),
                            high=99 + 2 * (i % 2), low=99 + 2 * (i % 2), close=99 + 2 * (i % 2), tick_volume=10)
                       for i in range(40)]
    snapshot = {"bridge_version": "isolated-demo-smoke", "symbol": "XAUUSD", "magic": 991188,
                "terminal_connected": True, "account_trade_mode": "DEMO", "account_login": 111001,
                "account_server": "ISOLATED-NO-BROKER", "demo_once_capable": True, "demo_once_consumed": False,
                "bridge_session_id": session, "server_time": START + 1, "tick_time_msc": (START + 1) * 1000,
                "bid": 100, "ask": 100.2, "point": .01, "tick_size": .01, "tick_value": 1.,
                "volume_min": .01, "volume_max": 1., "volume_step": .01, "stops_level": 10,
                "balance": 10000., "positions": [], "orders": [], "deals": [],
                "guardian": {"execution_locked": True, "execution_ready": False,
                             "terminal_trade_allowed": True, "mql_trade_allowed": True,
                             "max_volume": .01, "daily_loss_limit": 200., "reason": "ISOLATED_TEST"},
                "demo_once_guard": {"history_complete": True, "broker_day_start": START // 86400 * 86400,
                    "trades_today": 0, "consecutive_losses": 0, "last_exit_time": 0,
                    "day_start_balance": 10000., "daily_realized": 0., "symbol_positions": 0, "symbol_orders": 0,
                    "account_trade_allowed": True, "account_expert_allowed": True},
                "bars": {tf: rows[-1] for tf, rows in history.items()}, "bar_history": history}
    check((await request("bridge_snapshot", snapshot))["accepted"], "synthetic history accepted")
    def ticks(seq, values, complete=True):
        return {"symbol": "XAUUSD", "server_time": START + 180, "tick_batch": {
            "stream_id": "isolated-demo-test-ticks", "sequence": seq, "complete": complete,
            "ticks": [dict(time_msc=START * 1000 + offset, bid=price, ask=price + .2, last=0, flags=6)
                      for offset, price in values]}}
    await request("bridge_ticks", ticks(1, [(1000, 100)], False))
    context = (await request("demo_once_status"))["demo_once_context"]
    arm = {key: context[key] for key in ("account_login", "account_server", "symbol", "magic", "profile_hash")}
    arm.update(attempt_id=attempt, confirmed=True, max_volume=.01, duration_seconds=300)
    armed = await request("demo_once_arm", arm)
    check(armed["accepted"] and armed["demo_once"]["state"] == "ARMED", f"one-shot arm accepted: {armed}")
    pullback = await request("bridge_ticks", ticks(2, [(10000, 120), (50000, 104)]))
    check(pullback["strategy"]["state"] == "ARMED_SELL", "real strategy latches synthetic Z peak")
    check(pullback["demo_once_command"] is None, "no command before later-bar confirmation")
    snapshot.pop("bar_history")
    snapshot.update(server_time=START + 61, tick_time_msc=(START + 61) * 1000, bid=103, ask=103.2)
    snapshot["bars"]["M1"] = dict(time=START, open=100, high=120, low=100, close=104, tick_volume=20)
    await request("bridge_snapshot", snapshot)
    confirmation = ticks(3, [(61000, 103)])
    triggered = await request("bridge_ticks", confirmation)
    check(triggered["strategy"]["state"] == "TRIGGERED_SELL", "real strategy confirms next candle")
    command = triggered["demo_once_command"]
    check(isinstance(command, dict), f"one command emitted: {await request('demo_once_status')}")
    check(command["side"] == "SELL" and command["volume"] == .01, "bounded side and volume")
    check(command["sl"] > 103.2 and command["tp"] < 103, "protective initial stops")
    check(command["attempt_id"] == attempt and command["bridge_session_id"] == session, "authorization identity retained")
    check((await request("demo_once_status"))["demo_once"]["budget_consumed"], "budget consumed before delivery")
    check((await request("bridge_ticks", confirmation))["demo_once_command"] is None, "duplicate tick cannot resend")
    fake_result = {key: command[key] for key in ("attempt_id", "bridge_session_id", "account_login", "account_server", "symbol", "magic")}
    fake_result.update(order_send_called=True, retcode=10008, retcode_external=0, order_ticket=9001,
                       deal_ticket=9002, filled_volume=.01, fill_price=103, sl=command["sl"], tp=command["tp"],
                       status="FILLED", reason="ISOLATED_SYNTHETIC_DEAL_FIXTURE_NO_BROKER")
    result = await request("bridge_demo_once_result", fake_result)
    check(result["accepted"] and result["demo_once"]["state"] == "FILLED", "placed then verified deal accepted")
    heartbeat = await request("heartbeat")
    check(heartbeat["demo_once"]["deal_ticket"] == 9002, "receipt projected for desktop")
    check(not (await request("demo_once_arm", {**arm, "attempt_id": str(uuid4())}))["accepted"], "new UUID cannot renew budget")
    check((await request("bridge_demo_once_result", fake_result))["demo_once"]["state"] == "FILLED", "result replay remains filled")
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine_exe", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="xaupy-demo-once-smoke-") as temporary:
        with engine_session(str(args.engine_exe.resolve()), Path(temporary)) as stream:
            async def request(kind, payload=None):
                identifier = str(uuid4())
                envelope = {"schema_version": 1, "type": kind, "request_id": identifier,
                            "sent_at_utc": datetime.now(timezone.utc).isoformat(), "payload": payload or {}}
                stream.write((json.dumps(envelope) + "\n").encode()); stream.flush()
                reply = json.loads(stream.readline(1024 * 1024 + 1))
                expected = "config_active_ack" if kind == "config_active_get" else kind + "_ack"
                assert reply["request_id"] == identifier and reply["type"] == expected, reply
                data = reply["payload"]
                assert data["trading_enabled"] is False and data["execution_enabled"] is False
                return data
            count = asyncio.run(exercise_demo_once(request))
            print(f"Packaged one-shot: {count} checks passed; synthetic isolated protocol, no MT5/broker API.")


if __name__ == "__main__":
    main()
