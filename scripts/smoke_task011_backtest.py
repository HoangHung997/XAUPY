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


def task011_profile(base_profile: dict) -> dict:
    profile = copy.deepcopy(base_profile)
    profile["profile"]["name"] = "Task011 Packaged Smoke"
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
    profile["entry"]["mode"] = "MARKET"
    profile["risk"]["sizing_mode"] = "FIXED_LOT"
    profile["risk"]["fixed_lot"] = 0.10
    profile["risk"]["max_lot"] = 0.10
    profile["risk"]["max_open_positions"] = 1
    profile["risk"]["max_trades_per_day"] = 8
    profile["risk"]["cooldown_minutes"] = 0
    profile["risk"]["max_consecutive_losses"] = 8
    profile["risk"]["max_daily_loss_pct"] = 50.0
    profile["risk"]["stop_after_daily_target"] = False
    profile["stop_loss"]["mode"] = "FIXED"
    profile["stop_loss"]["fixed_price_units"] = 2.0
    profile["stop_loss"]["min_price_units"] = 0.5
    profile["stop_loss"]["max_price_units"] = 20.0
    profile["take_profit"]["mode"] = "FIXED"
    profile["take_profit"]["fixed_price_units"] = 3.0
    profile["management"]["breakeven_enabled"] = False
    profile["management"]["partial_close_enabled"] = False
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

    with tempfile.TemporaryDirectory(prefix="xaupy-task011-") as tmp:
        root = Path(tmp)
        dataset = root / "history.json"
        journal_dir = root / "journal"
        backtest_dir = root / "backtests"
        create_dataset(dataset)

        process1, sock1, file1 = start_engine(
            args.engine_exe,
            journal_dir,
            backtest_dir,
        )
        run_id = None
        result_hash = None
        try:
            heartbeat = exchange(file1, "heartbeat")
            assert heartbeat["type"] == "heartbeat_ack"
            assert heartbeat["payload"]["engine_version"] in {
                "0.11.0-task011",
                "0.12.0-task012",
            }
            assert heartbeat["payload"]["trading_enabled"] is False
            assert heartbeat["payload"]["execution_enabled"] is False

            active = exchange(file1, "config_active_get")
            profile = task011_profile(active["payload"]["profile"])
            applied = exchange(file1, "config_active_set", {"profile": profile})
            assert applied["type"] == "config_active_set_ack"
            assert applied["payload"]["applied"] is True
            assert applied["payload"]["execution_enabled"] is False

            inspected = exchange(
                file1,
                "backtest_dataset_inspect",
                {"path": str(dataset)},
            )
            assert inspected["type"] == "backtest_dataset_inspect_ack"
            assert inspected["payload"]["ok"] is True
            assert inspected["payload"]["dataset"]["bar_count"] == 8
            assert inspected["payload"]["dataset"]["metadata"]["symbol"] == "XAUUSD"

            request = {
                "path": str(dataset),
                "from_date": "2024-01-01",
                "to_date": "2024-01-01",
                "initial_balance": 10000.0,
                "spread_pips": 0.0,
                "commission_per_lot": 7.0,
            }
            first = exchange(file1, "backtest_run", request)
            second = exchange(file1, "backtest_run", request)

            assert first["type"] == "backtest_run_ack"
            assert second["type"] == "backtest_run_ack"
            assert first["payload"]["ok"] is True
            assert second["payload"]["ok"] is True
            assert first["payload"]["execution_enabled"] is False
            assert first["payload"]["trading_enabled"] is False

            result1 = first["payload"]["result"]
            result2 = second["payload"]["result"]
            assert result1["model"] == "M1_OHLC_PARITY_V1"
            assert result1["metrics"]["total_trades"] >= 1
            assert result1["result_hash"] == result2["result_hash"]
            assert result1["run_id"] != result2["run_id"]
            assert result1["trades"] == result2["trades"]

            first_trade = result1["trades"][0]
            assert first_trade["entry_time"] == first_trade["signal_time"] + 60
            run_id = result1["run_id"]
            result_hash = result1["result_hash"]

            history = exchange(
                file1,
                "backtest_history_query",
                {"limit": 20},
            )
            assert history["type"] == "backtest_history_query_ack"
            assert history["payload"]["ok"] is True
            assert len(history["payload"]["history"]) == 2

            journal = exchange(
                file1,
                "journal_query",
                {
                    "date_scope": "ALL",
                    "sources": ["Python Engine"],
                    "search": "Backtest completed",
                    "limit": 20,
                },
            )
            assert journal["type"] == "journal_query_ack"
            assert journal["payload"]["ok"] is True
            assert journal["payload"]["journal"]["total_matched"] == 2
        finally:
            stop_engine(process1, sock1, file1)

        assert run_id is not None
        assert result_hash is not None
        assert len(list(backtest_dir.glob("*.json"))) == 2

        process2, sock2, file2 = start_engine(
            args.engine_exe,
            journal_dir,
            backtest_dir,
        )
        try:
            history = exchange(
                file2,
                "backtest_history_query",
                {"limit": 20},
            )
            assert history["payload"]["ok"] is True
            assert any(
                item["run_id"] == run_id
                and item["result_hash"] == result_hash
                for item in history["payload"]["history"]
            )

            fetched = exchange(
                file2,
                "backtest_result_get",
                {
                    "run_id": run_id,
                    "trade_offset": 0,
                    "trade_limit": 1,
                },
            )
            assert fetched["payload"]["ok"] is True
            assert fetched["payload"]["result"]["result_hash"] == result_hash
            assert len(fetched["payload"]["result"]["trades"]) == 1
            assert fetched["payload"]["execution_enabled"] is False
            assert fetched["payload"]["trading_enabled"] is False
        finally:
            stop_engine(process2, sock2, file2)

    print("PASS: Task011 packaged deterministic Backtest parity/restart smoke test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
