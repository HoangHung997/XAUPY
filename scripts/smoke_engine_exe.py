from __future__ import annotations

import argparse
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


def envelope(message_type: str, request_id: str | None = None) -> dict:
    return {
        "schema_version": 1,
        "type": message_type,
        "request_id": request_id or str(uuid.uuid4()),
        "sent_at_utc": datetime.now(timezone.utc).isoformat(),
        "payload": {"component": "exe-smoke-test"},
    }


def exchange(file, message_type: str) -> dict:
    request = envelope(message_type)
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
                sock = socket.create_connection(("127.0.0.1", port), timeout=1)
                break
            except OSError as exc:
                last_error = exc
                time.sleep(0.25)

        if sock is None:
            raise RuntimeError(f"engine did not listen in time: {last_error}")

        sock.settimeout(3)
        file = sock.makefile("rwb")

        hello = exchange(file, "hello")
        assert hello["type"] == "hello_ack"
        assert hello["payload"]["trading_enabled"] is False

        heartbeat = exchange(file, "heartbeat")
        assert heartbeat["type"] == "heartbeat_ack"
        assert heartbeat["payload"]["trading_enabled"] is False

        shutdown = exchange(file, "shutdown")
        assert shutdown["type"] == "shutdown_ack"

        file.close()
        sock.close()
        sock = None

        return_code = process.wait(timeout=10)
        if return_code != 0:
            stdout, stderr = process.communicate(timeout=2)
            raise RuntimeError(
                f"engine returned {return_code}\n"
                f"stdout={stdout.decode(errors='replace')}\n"
                f"stderr={stderr.decode(errors='replace')}"
            )

        print("PASS: packaged xaupy-engine executable hello/heartbeat/shutdown smoke test")
        return 0
    finally:
        if sock is not None:
            sock.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
