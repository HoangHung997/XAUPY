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

        schema = exchange(file, "config_schema_get")
        assert schema["type"] == "config_schema_ack"
        assert schema["payload"]["config_schema"]["field_count"] == 133
        assert schema["payload"]["config_schema"]["timeframe_options"] == [
            "M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4"
        ]

        active = exchange(file, "config_active_get")
        profile = active["payload"]["profile"]
        assert profile["timeframes"] == {
            "direction": "M30",
            "pullback": "M5",
            "trigger": "M1",
        }

        changed = copy.deepcopy(profile)
        changed["profile"]["name"] = "Task006 Smoke"
        changed["timeframes"] = {
            "direction": "H1",
            "pullback": "M15",
            "trigger": "M3",
        }
        changed["pullback"]["rsi_buy_level"] = "45"
        changed["pullback"]["rsi_sell_level"] = "55"

        validate = exchange(file, "config_validate", {"profile": changed})
        assert validate["payload"]["valid"] is True
        normalized = validate["payload"]["profile"]
        assert normalized["pullback"]["rsi_buy_level"] == 45.0

        applied = exchange(file, "config_active_set", {"profile": changed})
        assert applied["type"] == "config_active_set_ack"
        assert applied["payload"]["applied"] is True
        assert applied["payload"]["profile"]["timeframes"] == {
            "direction": "H1",
            "pullback": "M15",
            "trigger": "M3",
        }

        current = exchange(file, "config_active_get")
        assert current["payload"]["profile"]["profile"]["name"] == "Task006 Smoke"

        invalid = copy.deepcopy(current["payload"]["profile"])
        invalid["execution"]["allow_real_account"] = True
        rejected = exchange(file, "config_active_set", {"profile": invalid})
        assert rejected["payload"]["applied"] is False
        assert any("allow_real_account" in item for item in rejected["payload"]["errors"])

        still_active = exchange(file, "config_active_get")
        assert still_active["payload"]["profile"]["execution"]["allow_real_account"] is False
        assert still_active["payload"]["profile"]["profile"]["name"] == "Task006 Smoke"

        assert applied["payload"]["execution_enabled"] is False
        assert applied["payload"]["trading_enabled"] is False

        shutdown = exchange(file, "shutdown", {"reason": "task006-ci-smoke"})
        assert shutdown["type"] == "shutdown_ack"

        file.close()
        sock.close()
        sock = None

        rc = process.wait(timeout=10)
        if rc != 0:
            raise RuntimeError(f"engine returned {rc}")

        print("PASS: Task006 packaged Engine active config/validation/safety smoke test")
        return 0
    finally:
        if sock is not None:
            sock.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
