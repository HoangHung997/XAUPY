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


def start_engine(
    engine_exe: str,
    journal_dir: Path,
    backtest_dir: Path,
    optimizer_dir: Path,
):
    port = free_port()
    env = dict(os.environ)
    env["XAUPY_LOG_DIR"] = str(journal_dir)
    env["XAUPY_BACKTEST_DIR"] = str(backtest_dir)
    env["XAUPY_OPTIMIZER_DIR"] = str(optimizer_dir)

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
        response = exchange(file, "shutdown", {"reason": "task012-ci-smoke"})
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


def create_dataset(path: Path, days: int = 12):
    start = 1_704_067_200
    closes = [100.0, 99.0, 98.0, 97.0, 100.0, 102.0, 101.0, 102.0]
    bars = []

    for day in range(days):
        previous = closes[0]
        day_start = start + day * 86400
        for index, close_value in enumerate(closes):
            close = close_value
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
                    "time": day_start + index * 60,
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


def task012_profile(base: dict) -> dict:
    profile = copy.deepcopy(base)
    profile["profile"]["name"] = "Task012 Packaged Smoke"
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
    profile["risk"]["max_lot"] = 1.0
    profile["risk"]["max_open_positions"] = 1
    profile["risk"]["max_trades_per_day"] = 20
    profile["risk"]["cooldown_minutes"] = 0
    profile["risk"]["max_consecutive_losses"] = 20
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
    for key in (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ):
        profile["sessions"][key] = True
    profile["news"]["enabled"] = False
    return profile


def wait_for_job(file, job_id: str, timeout_seconds: float = 45.0) -> dict:
    deadline = time.monotonic() + timeout_seconds
    latest = None
    while time.monotonic() < deadline:
        response = exchange(
            file,
            "optimizer_status",
            {"job_id": job_id},
        )
        assert response["type"] == "optimizer_status_ack"
        assert response["payload"]["ok"] is True
        assert response["payload"]["trading_enabled"] is False
        assert response["payload"]["execution_enabled"] is False
        latest = response["payload"]["status"]
        if latest["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return latest
        time.sleep(0.05)
    raise RuntimeError(f"optimizer did not finish in time: {latest}")


def sweep_request(dataset: Path) -> dict:
    return {
        "path": str(dataset),
        "from_date": "2024-01-01",
        "to_date": "2024-01-12",
        "initial_balance": 10000.0,
        "spread_pips": 0.0,
        "commission_per_lot": 0.0,
        "min_trades": 1,
        "max_workers": 2,
        "parameter_ranges": [
            {
                "path": "risk.fixed_lot",
                "min": 0.05,
                "max": 0.10,
                "step": 0.05,
            },
            {
                "path": "risk.cooldown_minutes",
                "min": 0,
                "max": 1,
                "step": 1,
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine_exe")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="xaupy-task012-") as tmp:
        root = Path(tmp)
        dataset = root / "history.json"
        journal_dir = root / "journal"
        backtest_dir = root / "backtests"
        optimizer_dir = root / "optimizations"
        create_dataset(dataset)

        process1, sock1, file1 = start_engine(
            args.engine_exe,
            journal_dir,
            backtest_dir,
            optimizer_dir,
        )
        sweep_run_ids: list[str] = []
        sweep_hash = None
        wf_run_id = None
        wf_hash = None

        try:
            heartbeat = exchange(file1, "heartbeat")
            assert heartbeat["type"] == "heartbeat_ack"
            assert heartbeat["payload"]["engine_version"] == "0.12.0-task012"
            assert heartbeat["payload"]["trading_enabled"] is False
            assert heartbeat["payload"]["execution_enabled"] is False
            assert heartbeat["payload"]["optimizer_status"]["status"] == "IDLE"

            active = exchange(file1, "config_active_get")
            profile = task012_profile(active["payload"]["profile"])
            applied = exchange(file1, "config_active_set", {"profile": profile})
            assert applied["payload"]["applied"] is True
            assert applied["payload"]["execution_enabled"] is False

            request = sweep_request(dataset)

            first_start = exchange(file1, "optimizer_start", request)
            assert first_start["type"] == "optimizer_start_ack"
            assert first_start["payload"]["ok"] is True
            first_job = first_start["payload"]["status"]["job_id"]

            # Long work is background; heartbeat must stay alive.
            during = exchange(file1, "heartbeat")
            assert during["type"] == "heartbeat_ack"
            assert during["payload"]["execution_enabled"] is False
            assert during["payload"]["optimizer_status"]["status"] in {
                "QUEUED",
                "RUNNING",
                "COMPLETED",
            }

            first_terminal = wait_for_job(file1, first_job)
            assert first_terminal["status"] == "COMPLETED"
            assert first_terminal["combination_count"] == 4
            first_run_id = first_terminal["result_run_id"]
            assert first_run_id
            sweep_run_ids.append(first_run_id)

            first_result = exchange(
                file1,
                "optimizer_result_get",
                {
                    "run_id": first_run_id,
                    "candidate_offset": 0,
                    "candidate_limit": 20,
                },
            )
            assert first_result["payload"]["ok"] is True
            sweep1 = first_result["payload"]["result"]
            assert sweep1["mode"] == "SWEEP"
            assert sweep1["objective"] == "ROBUST_SCORE_V1"
            assert sweep1["candidate_total"] == 4
            assert sweep1["eligible_count"] >= 1
            sweep_hash = sweep1["optimizer_hash"]

            heatmap = exchange(
                file1,
                "optimizer_heatmap",
                {
                    "run_id": first_run_id,
                    "x_path": "risk.fixed_lot",
                    "y_path": "risk.cooldown_minutes",
                    "metric": "net_profit",
                },
            )
            assert heatmap["payload"]["ok"] is True
            cells = heatmap["payload"]["heatmap"]["cells"]
            assert len(cells) == 4
            assert any(cell["samples"] > 0 for cell in cells)

            # Same work with different worker count must produce the same
            # deterministic optimizer hash and candidate ordering.
            request2 = copy.deepcopy(request)
            request2["max_workers"] = 1
            second_start = exchange(file1, "optimizer_start", request2)
            assert second_start["payload"]["ok"] is True
            second_terminal = wait_for_job(
                file1,
                second_start["payload"]["status"]["job_id"],
            )
            assert second_terminal["status"] == "COMPLETED"
            second_run_id = second_terminal["result_run_id"]
            sweep_run_ids.append(second_run_id)

            second_result = exchange(
                file1,
                "optimizer_result_get",
                {
                    "run_id": second_run_id,
                    "candidate_offset": 0,
                    "candidate_limit": 20,
                },
            )["payload"]["result"]
            assert second_result["optimizer_hash"] == sweep_hash
            assert second_result["candidates"] == sweep1["candidates"]

            wf_request = copy.deepcopy(request)
            wf_request.update(
                {
                    "folds": 3,
                    "train_ratio": 0.75,
                    "rolling": True,
                }
            )
            wf_start = exchange(file1, "walk_forward_start", wf_request)
            assert wf_start["payload"]["ok"] is True
            wf_terminal = wait_for_job(
                file1,
                wf_start["payload"]["status"]["job_id"],
                timeout_seconds=60,
            )
            assert wf_terminal["status"] == "COMPLETED"
            wf_run_id = wf_terminal["result_run_id"]

            wf_result = exchange(
                file1,
                "optimizer_result_get",
                {
                    "run_id": wf_run_id,
                    "candidate_offset": 0,
                    "candidate_limit": 10,
                },
            )["payload"]["result"]
            assert wf_result["mode"] == "WALK_FORWARD"
            assert wf_result["fold_count"] == 3
            assert wf_result["leakage_guard_passed"] is True
            assert 0.0 <= wf_result["aggregate"]["stability"] <= 1.0
            for fold in wf_result["folds"]:
                assert fold["selection_source"] == "TRAIN_ONLY"
                assert fold["leakage_guard_passed"] is True
                assert fold["train_to"] < fold["test_from"]
            wf_hash = wf_result["optimizer_hash"]

            journal = exchange(
                file1,
                "journal_query",
                {
                    "date_scope": "ALL",
                    "sources": ["Python Engine"],
                    "search": "optimization",
                    "limit": 100,
                },
            )
            assert journal["payload"]["ok"] is True
            tags = {event["tag"] for event in journal["payload"]["journal"]["events"]}
            assert "OPTIMIZER_START" in tags
            assert "OPTIMIZER_COMPLETE" in tags
            assert "WALK_FORWARD_START" in tags
            assert "WALK_FORWARD_COMPLETE" in tags
        finally:
            stop_engine(process1, sock1, file1)

        assert sweep_hash is not None
        assert wf_run_id is not None
        assert wf_hash is not None
        assert len(list(optimizer_dir.glob("*.json"))) == 3

        process2, sock2, file2 = start_engine(
            args.engine_exe,
            journal_dir,
            backtest_dir,
            optimizer_dir,
        )
        try:
            history = exchange(
                file2,
                "optimizer_history_query",
                {"limit": 20},
            )
            assert history["payload"]["ok"] is True
            ids = {item["run_id"] for item in history["payload"]["history"]}
            assert set(sweep_run_ids).issubset(ids)
            assert wf_run_id in ids

            fetched = exchange(
                file2,
                "optimizer_result_get",
                {
                    "run_id": wf_run_id,
                    "candidate_offset": 0,
                    "candidate_limit": 10,
                },
            )
            assert fetched["payload"]["ok"] is True
            assert fetched["payload"]["result"]["optimizer_hash"] == wf_hash
            assert fetched["payload"]["execution_enabled"] is False
            assert fetched["payload"]["trading_enabled"] is False
        finally:
            stop_engine(process2, sock2, file2)

    print("PASS: Task012 packaged optimizer/walk-forward reproducibility and restart smoke test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
