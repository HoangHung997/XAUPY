from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone


TIMEFRAMES = ("M1","M3","M5","M15","M30","H1","H2","H4")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def envelope(message_type: str, payload: dict) -> dict:
    return {
        "schema_version": 1,
        "type": message_type,
        "request_id": str(uuid.uuid4()),
        "sent_at_utc": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def exchange(file, message_type: str, payload: dict) -> dict:
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


def sample_snapshot() -> dict:
    bar = {
        "time": 1790240000,
        "open": 4280.0,
        "high": 4282.0,
        "low": 4279.0,
        "close": 4281.0,
        "tick_volume": 100,
    }
    return {
        "bridge_version": "0.3.0-task003",
        "symbol": "XAUUSD",
        "terminal_connected": True,
        "account_trade_mode": "DEMO",
        "bid": 4281.10,
        "ask": 4281.35,
        "guardian": {
            "execution_locked": True,
            "execution_ready": False,
            "reason": "TASK003_EXECUTION_LOCKED",
        },
        "bars": {tf: dict(bar) for tf in TIMEFRAMES},
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
        assert hello["payload"]["execution_enabled"] is False

        snap = exchange(bridge_file, "bridge_snapshot", sample_snapshot())
        assert snap["type"] == "bridge_snapshot_ack"
        assert snap["payload"]["command"] is None
        assert snap["payload"]["execution_enabled"] is False

        desktop_sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        desktop_sock.settimeout(3)
        sockets.append(desktop_sock)
        desktop_file = desktop_sock.makefile("rwb")

        heartbeat = exchange(desktop_file, "heartbeat", {"component": "ci-smoke"})
        bridge = heartbeat["payload"]["bridge"]
        assert bridge["connected"] is True
        assert bridge["symbol"] == "XAUUSD"
        assert bridge["execution_locked"] is True
        assert bridge["execution_ready"] is False

        unsupported = exchange(
            desktop_file,
            "trade_intent",
            {"symbol": "XAUUSD", "side": "BUY", "volume": 0.1},
        )
        assert unsupported["type"] == "error"
        assert unsupported["payload"]["execution_enabled"] is False

        shutdown = exchange(desktop_file, "shutdown", {"reason": "ci-smoke"})
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

        print("PASS: Task003 packaged Engine bridge/data/lock smoke test")
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
