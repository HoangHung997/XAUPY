from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone


TIMEFRAMES = ("M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4")


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


def snapshot() -> dict:
    bar = {
        "time": 1_800_300_000,
        "open": 4280.0,
        "high": 4283.0,
        "low": 4279.0,
        "close": 4282.0,
        "tick_volume": 250,
    }
    return {
        "bridge_version": "0.9.0-task009",
        "symbol": "XAUUSD",
        "magic": 991188,
        "terminal_connected": True,
        "account_trade_mode": "DEMO",
        "account_login": 12345678,
        "account_currency": "USD",
        "leverage": 100,
        "balance": 10000.0,
        "equity": 10000.0,
        "margin_free": 9950.0,
        "bid": 4282.0,
        "ask": 4282.3,
        "spread_points": 30.0,
        "digits": 2,
        "point": 0.01,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "stops_level": 10,
        "freeze_level": 5,
        "positions_count": 1,
        "orders_count": 1,
        "own_daily_realized": 43.5,
        "positions": [
            {
                "ticket": 32874561,
                "magic": 991188,
                "symbol": "XAUUSD",
                "side": "BUY",
                "volume": 0.10,
                "price_open": 4280.0,
                "price_current": 4282.0,
                "sl": 4275.0,
                "tp": 4290.0,
                "profit": 20.0,
                "swap": -1.0,
                "time": 1_800_299_000,
                "comment": "XAUPY",
            }
        ],
        "orders": [
            {
                "ticket": 32874570,
                "magic": 991188,
                "symbol": "XAUUSD",
                "type": "BUY STOP",
                "volume_initial": 0.10,
                "volume_current": 0.10,
                "price_open": 4285.0,
                "price_current": 4282.0,
                "sl": 4281.0,
                "tp": 4295.0,
                "state": "PLACED",
                "time_setup": 1_800_299_500,
                "comment": "XAUPY",
            }
        ],
        "deals": [
            {
                "ticket": 32874560,
                "order_ticket": 32874559,
                "magic": 991188,
                "symbol": "XAUUSD",
                "side": "SELL",
                "entry": "OUT",
                "volume": 0.10,
                "price_in": 4278.0,
                "price_out": 4282.1,
                "profit": 44.0,
                "commission": -0.5,
                "swap": 0.0,
                "realized_total": 43.5,
                "reason": "TP",
                "time": 1_800_298_000,
                "comment": "XAUPY",
            }
        ],
        "guardian": {
            "execution_locked": True,
            "execution_ready": False,
            "reason": "TASK003_EXECUTION_LOCKED",
            "daily_realized": 43.5,
            "daily_loss_limit": 200.0,
        },
        "bars": {tf: dict(bar) for tf in TIMEFRAMES},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine_exe")
    args = parser.parse_args()

    port = free_port()
    process = subprocess.Popen(
        [args.engine_exe, "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    sock = None
    try:
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
            raise RuntimeError("engine did not listen in time")

        sock.settimeout(4)
        file = sock.makefile("rwb")

        heartbeat = exchange(file, "heartbeat")
        assert heartbeat["type"] == "heartbeat_ack"
        assert heartbeat["payload"]["engine_version"] in {
            "0.9.0-task009",
            "0.10.0-task010",
            "0.11.0-task011",
        }
        assert heartbeat["payload"]["execution_enabled"] is False

        bridge = exchange(file, "bridge_snapshot", snapshot())
        assert bridge["type"] == "bridge_snapshot_ack"
        assert bridge["payload"]["execution_enabled"] is False

        heartbeat = exchange(file, "heartbeat")
        book = heartbeat["payload"]["orders_positions"]
        assert book["available"] is True
        assert book["positions"][0]["ticket"] == 32874561
        assert book["orders"][0]["ticket"] == 32874570
        assert book["deals"][0]["price_in"] == 4278.0
        assert book["deals"][0]["price_out"] == 4282.1
        assert book["open_pl"] == 19.0
        assert book["realized_pl"] == 43.5
        assert book["broker_execution_locked"] is True
        assert book["simulation_only"] is True

        intent_id = str(uuid.uuid4())
        request = {
            "intent_id": intent_id,
            "action": "CLOSE_POSITION",
            "confirmed": True,
            "ticket": 32874561,
        }
        simulated = exchange(file, "manual_action_simulate", request)
        assert simulated["type"] == "manual_action_simulate_ack"
        assert simulated["payload"]["accepted"] is True
        assert simulated["payload"]["simulated"] is True
        assert simulated["payload"]["broker_mutated"] is False
        assert simulated["payload"]["execution_enabled"] is False
        assert simulated["payload"]["trading_enabled"] is False
        assert simulated["payload"]["preview"]["broker_request_sent"] is False

        replay = exchange(file, "manual_action_simulate", request)
        assert replay["payload"]["code"] == simulated["payload"]["code"]
        assert replay["payload"]["preview"] == simulated["payload"]["preview"]

        conflict = exchange(
            file,
            "manual_action_simulate",
            {**request, "ticket": 999999},
        )
        assert conflict["payload"]["accepted"] is False
        assert conflict["payload"]["code"] == "INTENT_ID_CONFLICT"

        legacy_trade = exchange(
            file,
            "trade_intent",
            {"symbol": "XAUUSD", "side": "BUY", "volume": 0.1},
        )
        assert legacy_trade["type"] == "error"
        assert legacy_trade["payload"]["code"] == "UNSUPPORTED_MESSAGE"
        assert legacy_trade["payload"]["execution_enabled"] is False

        shutdown = exchange(file, "shutdown", {"reason": "task009-ci-smoke"})
        assert shutdown["type"] == "shutdown_ack"

        file.close()
        sock.close()
        sock = None

        rc = process.wait(timeout=10)
        if rc != 0:
            raise RuntimeError(f"engine returned {rc}")

        print("PASS: Task009 packaged order-book/manual-simulation safety smoke test")
        return 0
    finally:
        if sock is not None:
            sock.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
