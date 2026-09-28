"""Packaged maintenance acceptance using temporary state and no broker actions."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import uuid

from _smoke_runtime import isolated_environment


def exchange(stream, message_type: str, payload: dict | None = None) -> dict:
    request_id = str(uuid.uuid4())
    request = {"schema_version": 1, "type": message_type, "request_id": request_id,
               "sent_at_utc": datetime.now(timezone.utc).isoformat(), "payload": payload or {}}
    stream.write((json.dumps(request, separators=(",", ":")) + "\n").encode())
    stream.flush()
    response = json.loads(stream.readline().decode())
    assert response["request_id"] == request_id, "response correlation mismatch"
    expected_type = "config_active_ack" if message_type == "config_active_get" else message_type + "_ack"
    assert response["type"] == expected_type, response
    result = response["payload"]
    assert result["trading_enabled"] is False and result["execution_enabled"] is False
    return result


@contextmanager
def engine_session(executable: str, runtime: Path):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    environment = isolated_environment(runtime)
    instance = uuid.uuid4().hex
    environment["XAUPY_INSTANCE_ID"] = instance
    process = subprocess.Popen([executable, "--host", "127.0.0.1", "--port", str(port)],
                               env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    sock = None
    stream = None
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if process.poll() is not None:
                out, err = process.communicate()
                raise RuntimeError(f"Engine exited: {out.decode(errors='replace')} {err.decode(errors='replace')}")
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=1)
                break
            except OSError:
                time.sleep(0.15)
        if sock is None:
            raise TimeoutError("Engine did not start")
        sock.settimeout(15)
        stream = sock.makefile("rwb")
        hello = exchange(stream, "hello", {"component": "maintenance-smoke"})
        assert hello["engine_instance_id"] == instance, "launched process identity missing"
        assert hello["engine_version"] == "1.0.0-dev"
        yield stream
    finally:
        if stream is not None and process.poll() is None:
            try:
                exchange(stream, "shutdown", {"reason": "maintenance-smoke-complete"})
                process.wait(timeout=10)
            except (OSError, ValueError, AssertionError, subprocess.TimeoutExpired):
                pass
        if stream is not None:
            stream.close()
        if sock is not None:
            sock.close()
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
            else:
                process.kill()
            process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine_exe")
    executable = str(Path(parser.parse_args().engine_exe).resolve())
    with tempfile.TemporaryDirectory(prefix="xaupy-maintenance-smoke-") as temporary:
        runtime = Path(temporary)
        with engine_session(executable, runtime) as stream:
            diagnostic = exchange(stream, "diagnostics_get")
            assert diagnostic["ok"]
            checks = {item["name"]: item["status"] for item in diagnostic["diagnostics"]["checks"]}
            assert checks["Python Engine"] == checks["Local IPC"] == "OK"
            assert checks["EA Bridge"] == checks["Market data"] == "WAIT"
            assert checks["Execution"] == "OFF"

            settings = exchange(stream, "settings_get")["settings"]
            settings["startup"]["auto_restart_engine"] = False
            settings["backup"]["keep_count"] = 2
            assert exchange(stream, "settings_set", {"settings": settings})["ok"]
            profile = exchange(stream, "config_active_get")["profile"]
            profile["profile"]["name"] = "Maintenance recovery acceptance"
            assert exchange(stream, "config_active_set", {"profile": profile})["applied"]
            backup = exchange(stream, "backup_create")["backup"]["id"]
            profile["profile"]["name"] = "Temporary changed profile"
            assert exchange(stream, "config_active_set", {"profile": profile})["applied"]
            restored = exchange(stream, "backup_restore", {"backup_id": backup})
            assert restored["ok"]
            assert len(restored["backups"]) <= 2
            assert exchange(stream, "config_active_get")["profile"]["profile"]["name"] == "Maintenance recovery acceptance"
            settings["safety"]["allow_real_account"] = True
            assert exchange(stream, "settings_set", {"settings": settings})["ok"]
            execution=exchange(stream, 'diagnostics_get')['diagnostics']['execution']
            assert execution['mode']=='OFF' and not execution['execution_enabled']
            assert not exchange(stream, "backup_restore", {"backup_id": "../runtime-v1.json"})["ok"]

        with engine_session(executable, runtime) as stream:
            saved = exchange(stream, "settings_get")
            assert not saved["settings"]["startup"]["auto_restart_engine"]
            assert saved["settings"]["safety"]["allow_real_account"]
            assert "reconciliation" in saved["recovery_message"]
            assert exchange(stream, "config_active_get")["profile"]["profile"]["name"] == "Maintenance recovery acceptance"

        state_path = runtime / "state" / "runtime-v1.json"
        state_path.write_text("{broken state", encoding="utf-8")
        with engine_session(executable, runtime) as stream:
            recovered = exchange(stream, "settings_get")
            assert recovered["ok"] and "rejected" in recovered["recovery_message"]
            assert recovered["settings"]["startup"]["auto_restart_engine"]
            assert state_path.read_text(encoding="utf-8") == "{broken state"
    print("Task014/015 packaged diagnostics, settings/restart, safe backup/restore, corrupt recovery and process identity: PASS")


if __name__ == "__main__":
    main()
