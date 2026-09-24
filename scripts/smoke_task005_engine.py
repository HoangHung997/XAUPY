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


def bridge_snapshot() -> dict:
    bars = {}
    for index, tf in enumerate(TIMEFRAMES):
        bars[tf] = {
            "time": 1790240000 + index * 60,
            "open": 4280.0 + index,
            "high": 4282.0 + index,
            "low": 4279.0 + index,
            "close": 4281.0 + index,
            "tick_volume": 100 + index,
        }

    return {
        "bridge_version": "0.3.0-task003",
        "symbol": "XAUUSD",
        "terminal_connected": True,
        "account_trade_mode": "DEMO",
        "account_login": 123456,
        "account_currency": "USD",
        "balance": 10000.0,
        "equity": 10025.5,
        "margin_free": 9900.25,
        "bid": 4281.10,
        "ask": 4281.35,
        "spread_points": 25.0,
        "positions_count": 1,
        "orders_count": 2,
        "guardian": {
            "execution_locked": True,
            "execution_ready": False,
            "reason": "TASK003_EXECUTION_LOCKED",
        },
        "bars": bars,
    }


def connect_with_retry(port: int, process: subprocess.Popen):
    deadline = time.monotonic() + 25
    last_error = None

    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=2)
            raise RuntimeError(
                f"engine exited early rc={process.returncode}\n"
                f"stdout={stdout.decode(errors='replace')}\n"
                f"stderr={stderr.decode(errors='replace')}"
            )

        try:
            return socket.create_connection(("127.0.0.1", port), timeout=1)
        except OSError as exc:
            last_error = exc
            time.sleep(0.25)

    raise RuntimeError(f"engine did not listen in time: {last_error}")


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

    sockets = []
    try:
        bridge_sock = connect_with_retry(port, process)
        bridge_sock.settimeout(3)
        sockets.append(bridge_sock)
        bridge_file = bridge_sock.makefile("rwb")

        hello = exchange(
            bridge_file,
            "bridge_hello",
            {"bridge_version": "0.3.0-task003", "symbol": "XAUUSD"},
        )
        assert hello["type"] == "bridge_hello_ack"

        snap = exchange(bridge_file, "bridge_snapshot", bridge_snapshot())
        assert snap["type"] == "bridge_snapshot_ack"

        desktop_sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        desktop_sock.settimeout(3)
        sockets.append(desktop_sock)
        desktop_file = desktop_sock.makefile("rwb")

        config = exchange(desktop_file, "config_defaults_get")
        profile = config["payload"]["profile"]
        assert profile["timeframes"] == {
            "direction": "M30",
            "pullback": "M5",
            "trigger": "M1",
        }

        heartbeat = exchange(desktop_file, "heartbeat", {"component": "task005-smoke"})
        overview = heartbeat["payload"]["overview"]

        assert overview["available"] is True
        assert overview["symbol"] == "XAUUSD"
        assert overview["account_trade_mode"] == "DEMO"
        assert overview["account_currency"] == "USD"
        assert overview["bid"] == 4281.10
        assert overview["ask"] == 4281.35
        assert overview["balance"] == 10000.0
        assert overview["equity"] == 10025.5
        assert overview["margin_free"] == 9900.25
        assert overview["positions_count"] == 1
        assert overview["orders_count"] == 2
        assert set(overview["bars"]) == set(TIMEFRAMES)

        assert heartbeat["payload"]["execution_enabled"] is False
        assert heartbeat["payload"]["trading_enabled"] is False

        shutdown = exchange(desktop_file, "shutdown", {"reason": "task005-ci-smoke"})
        assert shutdown["type"] == "shutdown_ack"

        bridge_file.close()
        desktop_file.close()
        for sock in sockets:
            sock.close()
        sockets.clear()

        rc = process.wait(timeout=10)
        if rc != 0:
            stdout, stderr = process.communicate(timeout=2)
            raise RuntimeError(
                f"engine returned {rc}\n"
                f"stdout={stdout.decode(errors='replace')}\n"
                f"stderr={stderr.decode(errors='replace')}"
            )

        print("PASS: Task005 packaged Engine overview/config/bridge smoke test")
        return 0
    finally:
        for sock in sockets:
            try:
                sock.close()
            except OSError:
                pass

        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
