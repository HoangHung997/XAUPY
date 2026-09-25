from __future__ import annotations

import argparse
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


def start_engine(engine_exe: str, journal_dir: Path):
    port = free_port()
    env = dict(os.environ)
    env["XAUPY_LOG_DIR"] = str(journal_dir)

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

    sock.settimeout(4)
    return process, sock, sock.makefile("rwb")


def stop_engine(process, sock, file):
    try:
        shutdown = exchange(file, "shutdown", {"reason": "task010-ci-smoke"})
        assert shutdown["type"] == "shutdown_ack"
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine_exe")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="xaupy-task010-") as tmp:
        journal_dir = Path(tmp)

        process1, sock1, file1 = start_engine(args.engine_exe, journal_dir)
        first_sequence = None
        bookmarked_sequence = None
        try:
            heartbeat = exchange(file1, "heartbeat")
            assert heartbeat["type"] == "heartbeat_ack"
            assert heartbeat["payload"]["engine_version"] in {
                "0.10.0-task010",
                "0.11.0-task011",
            }
            assert heartbeat["payload"]["execution_enabled"] is False
            assert heartbeat["payload"]["trading_enabled"] is False
            assert heartbeat["payload"]["journal_summary"]["schema_version"] == 1
            assert heartbeat["payload"]["journal_summary"]["total"] >= 1

            queried = exchange(
                file1,
                "journal_query",
                {
                    "date_scope": "ALL",
                    "levels": ["INFO", "WARN", "ERROR", "DEBUG"],
                    "limit": 500,
                },
            )
            assert queried["type"] == "journal_query_ack"
            assert queried["payload"]["ok"] is True
            events = queried["payload"]["journal"]["events"]
            assert events
            first_sequence = queried["payload"]["journal"]["latest_sequence"]
            bookmarked_sequence = events[0]["sequence"]

            bookmarked = exchange(
                file1,
                "journal_bookmark_set",
                {
                    "sequence": bookmarked_sequence,
                    "bookmarked": True,
                },
            )
            assert bookmarked["type"] == "journal_bookmark_set_ack"
            assert bookmarked["payload"]["ok"] is True
            assert bookmarked["payload"]["event"]["bookmarked"] is True
            assert bookmarked["payload"]["execution_enabled"] is False
        finally:
            stop_engine(process1, sock1, file1)

        assert (journal_dir / "journal-v1.jsonl").is_file()
        assert (journal_dir / "bookmarks-v1.json").is_file()

        process2, sock2, file2 = start_engine(args.engine_exe, journal_dir)
        try:
            replayed = exchange(
                file2,
                "journal_query",
                {
                    "date_scope": "ALL",
                    "bookmarks_only": True,
                    "limit": 500,
                },
            )
            assert replayed["type"] == "journal_query_ack"
            assert replayed["payload"]["ok"] is True
            bookmarks = replayed["payload"]["journal"]["events"]
            assert any(
                event["sequence"] == bookmarked_sequence and event["bookmarked"]
                for event in bookmarks
            )
            assert replayed["payload"]["journal"]["latest_sequence"] > first_sequence
            assert replayed["payload"]["execution_enabled"] is False
            assert replayed["payload"]["trading_enabled"] is False
        finally:
            stop_engine(process2, sock2, file2)

        lines = (journal_dir / "journal-v1.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        assert len(lines) >= 4
        decoded = [json.loads(line) for line in lines if line.strip()]
        sequences = [item["sequence"] for item in decoded]
        assert sequences == sorted(sequences)
        assert len(sequences) == len(set(sequences))

    print("PASS: Task010 packaged structured journal replay/bookmark smoke test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
