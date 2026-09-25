from __future__ import annotations

import argparse
import copy
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


def bridge_snapshot(index: int, direction: float, pullback: float, trigger: float) -> dict:
    selected = {"M30": direction, "M5": pullback, "M1": trigger}
    timestamp = 1_800_200_000 + index * 60
    bars = {}
    for timeframe in TIMEFRAMES:
        close = float(selected.get(timeframe, trigger))
        bars[timeframe] = {
            "time": timestamp,
            "open": close - 0.1,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "tick_volume": 200 + index,
        }

    return {
        "bridge_version": "0.3.0-task003",
        "symbol": "XAUUSD",
        "terminal_connected": True,
        "account_trade_mode": "DEMO",
        "bid": float(trigger),
        "ask": float(trigger) + 0.2,
        "guardian": {
            "execution_locked": True,
            "execution_ready": False,
            "reason": "TASK003_EXECUTION_LOCKED",
        },
        "bars": bars,
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

        sock.settimeout(3)
        file = sock.makefile("rwb")

        heartbeat = exchange(file, "heartbeat")
        assert heartbeat["type"] == "heartbeat_ack"
        # Strategy regression smoke is intentionally forward-compatible:
        # later tasks may advance the Engine version while preserving Task 007 behavior.
        assert heartbeat["payload"]["engine_version"] in {
            "0.7.0-task007",
            "0.8.0-task008",
            "0.9.0-task009",
            "0.10.0-task010",
        }
        assert heartbeat["payload"]["strategy"]["state"] == "STALE"
        assert heartbeat["payload"]["strategy"]["execution_enabled"] is False

        active = exchange(file, "config_active_get")
        profile = copy.deepcopy(active["payload"]["profile"])
        profile["profile"]["name"] = "Task007 Packaged Smoke"
        profile["direction"]["ma_period"] = 3
        profile["pullback"]["rsi_period"] = 2
        profile["pullback"]["rsi_buy_level"] = 40.0
        profile["pullback"]["rsi_sell_level"] = 60.0
        profile["pullback"]["z_enabled"] = False
        profile["trigger"]["rsi_period"] = 2
        profile["trigger"]["rsi_reversal_delta"] = 10.0
        profile["trigger"]["z_enabled"] = False
        profile["filters"]["adx"]["enabled"] = False
        profile["filters"]["atr"]["enabled"] = False
        profile["filters"]["open"]["enabled"] = False
        profile["direction"]["open_filter_enabled"] = False

        applied = exchange(file, "config_active_set", {"profile": profile})
        assert applied["payload"]["applied"] is True
        assert applied["payload"]["execution_enabled"] is False

        direction = [100, 101, 102, 103, 104, 105]
        pullback = [100, 99, 98, 97, 96, 95]
        trigger = [100, 99, 98, 97, 96, 98]
        states = []

        for index in range(len(direction)):
            response = exchange(
                file,
                "bridge_snapshot",
                bridge_snapshot(index, direction[index], pullback[index], trigger[index]),
            )
            assert response["type"] == "bridge_snapshot_ack"
            strategy = response["payload"]["strategy"]
            states.append(strategy["state"])
            assert strategy["trading_enabled"] is False
            assert strategy["execution_enabled"] is False

        assert "ARMED_BUY" in states
        assert states[-1] == "TRIGGERED_BUY"
        assert strategy["last_signal"]["side"] == "BUY"
        assert strategy["signal_sequence"] == 1

        final_heartbeat = exchange(file, "heartbeat")
        assert final_heartbeat["payload"]["strategy"]["state"] == "TRIGGERED_BUY"
        assert final_heartbeat["payload"]["strategy"]["signal_sequence"] == 1
        assert final_heartbeat["payload"]["execution_enabled"] is False
        assert final_heartbeat["payload"]["trading_enabled"] is False

        shutdown = exchange(file, "shutdown", {"reason": "task007-ci-smoke"})
        assert shutdown["type"] == "shutdown_ack"

        file.close()
        sock.close()
        sock = None

        rc = process.wait(timeout=10)
        if rc != 0:
            raise RuntimeError(f"engine returned {rc}")

        print("PASS: Task007 packaged Engine deterministic strategy/safety smoke test")
        return 0
    finally:
        if sock is not None:
            sock.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
