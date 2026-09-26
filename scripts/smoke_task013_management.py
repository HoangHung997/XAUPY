from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def envelope(message_type: str, payload: dict | None = None) -> dict:
    return {
        "schema_version": 1,
        "type": message_type,
        "request_id": str(uuid.uuid4()),
        "sent_at_utc": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
    }


def exchange(file, message_type: str, payload: dict | None = None) -> dict:
    request = envelope(message_type, payload)
    file.write((json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8"))
    file.flush()
    line = file.readline()
    if not line:
        raise RuntimeError(f"engine closed connection during {message_type}")
    response = json.loads(line.decode("utf-8"))
    if response["request_id"] != request["request_id"]:
        raise RuntimeError(f"{message_type} request_id mismatch")
    return response


def start_engine(engine_exe: str, journal_dir: Path, backtest_dir: Path):
    port = free_port()
    env = dict(os.environ)
    env["XAUPY_LOG_DIR"] = str(journal_dir)
    env["XAUPY_BACKTEST_DIR"] = str(backtest_dir)

    process = subprocess.Popen(
        [engine_exe, "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    sock = None
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=2)
            raise RuntimeError(
                f"engine exited early rc={process.returncode}\n"
                f"stdout={stdout.decode(errors='replace')}\n"
                f"stderr={stderr.decode(errors='replace')}"
            )
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=1)
            break
        except OSError:
            time.sleep(0.25)

    if sock is None:
        process.kill()
        process.wait(timeout=5)
        raise RuntimeError("engine did not listen in time")

    sock.settimeout(15)
    return process, sock, sock.makefile("rwb")


def stop_engine(process, sock, file):
    try:
        response = exchange(file, "shutdown", {"reason": "task011-ci-smoke"})
        assert response["type"] == "shutdown_ack"
    finally:
        try:
            file.close()
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass

    rc = process.wait(timeout=10)
    if rc != 0:
        raise RuntimeError(f"engine returned {rc}")


def create_dataset(path: Path):
    start = 1_704_067_200
    closes = [100.0, 99.0, 98.0, 97.0, 100.0, 102.0, 101.0, 102.0]
    bars = []
    previous = closes[0]
    for index, close in enumerate(closes):
        open_price = previous if index else close
        high = max(open_price, close) + 0.2
        low = min(open_price, close) - 0.2
        if index == 5:
            open_price = 100.0
            high = 104.0
            low = 99.0
            close = 102.0
        bars.append(
            {
                "time": start + index * 60,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "tick_volume": 100 + index,
            }
        )
        previous = close

    payload = {
        "schema_version": 1,
        "symbol": "XAUUSD",
        "timeframe": "M1",
        "point_size": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "timezone_offset_minutes": 0,
        "bars": bars,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def task013_profile(base_profile: dict) -> dict:
    profile = copy.deepcopy(base_profile)
    profile["profile"]["name"] = "Task013 Packaged Smoke"
    profile["strategy"]["allow_buy"] = True
    profile["strategy"]["allow_sell"] = False
    profile["timeframes"] = {
        "direction": "M1",
        "pullback": "M1",
        "trigger": "M1",
    }
    profile["direction"]["ma_enabled"] = False
    profile["direction"]["open_filter_enabled"] = False
    profile["pullback"]["rsi_enabled"] = False
    profile["pullback"]["z_enabled"] = False
    profile["trigger"]["rsi_enabled"] = True
    profile["trigger"]["rsi_period"] = 2
    profile["trigger"]["rsi_reversal_delta"] = 10.0
    profile["trigger"]["z_enabled"] = False
    profile["filters"]["adx"]["enabled"] = False
    profile["filters"]["atr"]["enabled"] = False
    profile["filters"]["open"]["enabled"] = False

    profile["entry"]["mode"] = "STOP_CONFIRM"
    profile["entry"]["pending_buffer_price_units"] = 0.10
    profile["entry"]["pending_expiration_minutes"] = 5
    profile["entry"]["cancel_on_opposite_setup"] = True
    profile["entry"]["cancel_on_direction_change"] = True
    profile["entry"]["max_signal_age_bars"] = 5

    profile["risk"]["sizing_mode"] = "FIXED_LOT"
    profile["risk"]["fixed_lot"] = 0.10
    profile["risk"]["max_lot"] = 0.10
    profile["risk"]["max_open_positions"] = 1
    profile["risk"]["max_trades_per_day"] = 8
    profile["risk"]["cooldown_minutes"] = 0
    profile["risk"]["max_consecutive_losses"] = 8
    profile["risk"]["max_daily_loss_pct"] = 50.0
    profile["risk"]["stop_after_daily_target"] = False

    profile["stop_loss"]["mode"] = "ATR"
    profile["stop_loss"]["atr_timeframe"] = "M1"
    profile["stop_loss"]["atr_period"] = 2
    profile["stop_loss"]["atr_multiplier"] = 1.0
    profile["stop_loss"]["min_price_units"] = 0.5
    profile["stop_loss"]["max_price_units"] = 20.0

    profile["take_profit"]["mode"] = "ZRSI_DYNAMIC"
    profile["take_profit"]["fixed_price_units"] = 5.0
    profile["take_profit"]["dynamic"]["near_tp_distance"] = 2.0
    profile["take_profit"]["dynamic"]["extend_use_z"] = False
    profile["take_profit"]["dynamic"]["extend_use_rsi"] = True
    profile["take_profit"]["dynamic"]["extend_logic"] = "EITHER"
    profile["take_profit"]["dynamic"]["exit_rsi_reverse_delta"] = 4.0
    profile["take_profit"]["dynamic"]["lock_sl_at_original_tp"] = True
    profile["take_profit"]["dynamic"]["lock_profit_buffer"] = 0.0
    profile["take_profit"]["dynamic"]["max_extension_price_units"] = 3.0
    profile["take_profit"]["dynamic"]["max_extension_minutes"] = 15
    profile["take_profit"]["dynamic"]["emergency_server_tp_enabled"] = True
    profile["take_profit"]["dynamic"]["emergency_server_tp_price_units"] = 10.0

    profile["management"]["breakeven_enabled"] = False
    profile["management"]["partial_close_enabled"] = True
    profile["management"]["partial_close_at_rr"] = 1.0
    profile["management"]["partial_close_percent"] = 50.0
    profile["management"]["trailing_enabled"] = False
    profile["management"]["sl_tighten_mode"] = "OFF"

    profile["sessions"]["timezone"] = "UTC"
    profile["sessions"]["session1_enabled"] = False
    profile["sessions"]["session2_enabled"] = False
    profile["news"]["enabled"] = False
    return profile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine_exe")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="xaupy-task013-") as tmp:
        root = Path(tmp)
        dataset = root / "history.json"
        journal_dir = root / "journal"
        backtest_dir = root / "backtests"
        create_dataset(dataset)

        process, sock, file = start_engine(
            args.engine_exe,
            journal_dir,
            backtest_dir,
        )
        try:
            heartbeat = exchange(file, "heartbeat")
            assert heartbeat["type"] == "heartbeat_ack"
            assert heartbeat["payload"]["engine_version"] == "0.13.0-task013"
            assert heartbeat["payload"]["trading_enabled"] is False
            assert heartbeat["payload"]["execution_enabled"] is False

            active = exchange(file, "config_active_get")
            profile = task013_profile(active["payload"]["profile"])
            applied = exchange(file, "config_active_set", {"profile": profile})
            assert applied["type"] == "config_active_set_ack"
            assert applied["payload"]["applied"] is True
            assert applied["payload"]["execution_enabled"] is False

            request = {
                "path": str(dataset),
                "from_date": "2024-01-01",
                "to_date": "2024-01-01",
                "initial_balance": 10000.0,
                "spread_pips": 0.0,
                "commission_per_lot": 2.0,
            }
            first = exchange(file, "backtest_run", request)
            second = exchange(file, "backtest_run", request)

            assert first["type"] == "backtest_run_ack"
            assert first["payload"]["ok"] is True
            assert second["payload"]["ok"] is True
            assert first["payload"]["trading_enabled"] is False
            assert first["payload"]["execution_enabled"] is False

            result1 = first["payload"]["result"]
            result2 = second["payload"]["result"]
            assert result1["model"] == "M1_OHLC_PARITY_V1"
            assert result1["result_hash"] == result2["result_hash"]
            assert result1["trades"] == result2["trades"]
            assert result1["pending_entry_events"] == result2["pending_entry_events"]
            assert result1["metrics"]["total_trades"] >= 1

            events = result1["pending_entry_events"]
            assert any(item["event"] == "CREATED" for item in events)
            assert any(item["event"] == "TRIGGERED" for item in events)

            trade = result1["trades"][0]
            assert trade["entry_mode"] == "STOP_CONFIRM"
            assert trade["pending_trigger_price"] is not None
            assert trade["original_tp"] != trade["hard_tp"]
            assert trade["partial_close_applied"] is True
            assert trade["partial_close"] is not None
            assert trade["dynamic_extended"] is True
            assert trade["exit_reason"] in {
                "ZRSI_REVERSAL",
                "DYNAMIC_HARD_TP",
                "DYNAMIC_HARD_TP_GAP",
                "DYNAMIC_MAX_TIME",
                "END_OF_DATA",
            }

            history = exchange(
                file,
                "backtest_history_query",
                {"limit": 20},
            )
            assert history["payload"]["ok"] is True
            assert len(history["payload"]["history"]) == 2

            journal = exchange(
                file,
                "journal_query",
                {
                    "date_scope": "ALL",
                    "sources": ["Python Engine"],
                    "search": "Backtest completed",
                    "limit": 20,
                },
            )
            assert journal["payload"]["journal"]["total_matched"] == 2
        finally:
            stop_engine(process, sock, file)

    print(
        "PASS: Task013 packaged STOP_CONFIRM/ATR/ZRSI/partial-management smoke test"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
