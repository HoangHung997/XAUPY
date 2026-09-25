from __future__ import annotations

from copy import deepcopy
import asyncio
import json
import pathlib
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.config_schema import default_profile
from xaupy_engine.contracts import Envelope
from xaupy_engine.optimizer import OptimizerEngine
from xaupy_engine.server import EngineServer


def optimizer_profile():
    profile = default_profile()
    profile["profile"]["name"] = "Task012 IPC"
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
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday"
    ):
        profile["sessions"][key] = True
    profile["news"]["enabled"] = False
    return profile


def write_dataset(path: pathlib.Path, days=12):
    start = 1_704_067_200
    bars = []
    closes = [100.0, 99.0, 98.0, 97.0, 100.0, 102.0, 101.0, 102.0]
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


async def exchange(reader, writer, message_type, payload=None):
    request = Envelope.create(message_type, payload or {})
    writer.write((request.to_json() + "\n").encode("utf-8"))
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=5)
    response = Envelope.from_json(line.decode("utf-8").rstrip("\r\n"))
    if response.request_id != request.request_id:
        raise AssertionError("response request_id mismatch")
    return response


class Task012OptimizerProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temp.name)
        self.dataset_path = root / "history.json"
        write_dataset(self.dataset_path, days=12)
        self.server = EngineServer(
            port=0,
            journal_dir=root / "journal",
            backtest_dir=root / "backtests",
            optimizer_dir=root / "optimizations",
        )
        self.server.active_profile = optimizer_profile()
        self.server.strategy.set_profile(self.server.active_profile)
        await self.server.start()

    async def asyncTearDown(self):
        await asyncio.wait_for(self.server.close(), timeout=15)
        self.temp.cleanup()

    async def connect(self):
        return await asyncio.open_connection(
            "127.0.0.1",
            self.server.bound_port,
        )

    def sweep_request(self):
        return {
            "path": str(self.dataset_path),
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

    async def wait_for_terminal(self, reader, writer, job_id):
        deadline = time.monotonic() + 10
        latest = None
        while time.monotonic() < deadline:
            response = await exchange(
                reader,
                writer,
                "optimizer_status",
                {"job_id": job_id},
            )
            self.assertTrue(response.payload["ok"])
            latest = response.payload["status"]
            if latest["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                return latest
            await asyncio.sleep(0.03)
        self.fail(f"optimizer job did not finish: {latest}")

    async def test_sweep_status_result_heatmap_history_delete_and_journal(self):
        reader, writer = await self.connect()

        start = await exchange(
            reader,
            writer,
            "optimizer_start",
            self.sweep_request(),
        )
        self.assertEqual("optimizer_start_ack", start.type)
        self.assertTrue(start.payload["ok"])
        self.assertFalse(start.payload["trading_enabled"])
        self.assertFalse(start.payload["execution_enabled"])
        job_id = start.payload["status"]["job_id"]

        terminal = await self.wait_for_terminal(reader, writer, job_id)
        self.assertEqual("COMPLETED", terminal["status"])
        self.assertEqual(4, terminal["combination_count"])
        self.assertEqual(terminal["total_work"], terminal["completed_work"])
        run_id = terminal["result_run_id"]
        self.assertTrue(run_id)

        result = await exchange(
            reader,
            writer,
            "optimizer_result_get",
            {
                "run_id": run_id,
                "candidate_offset": 0,
                "candidate_limit": 10,
            },
        )
        self.assertTrue(result.payload["ok"])
        sweep = result.payload["result"]
        self.assertEqual("SWEEP", sweep["mode"])
        self.assertEqual("ROBUST_SCORE_V1", sweep["objective"])
        self.assertEqual(4, sweep["candidate_total"])
        self.assertEqual(64, len(sweep["optimizer_hash"]))
        self.assertGreaterEqual(sweep["eligible_count"], 1)

        heatmap = await exchange(
            reader,
            writer,
            "optimizer_heatmap",
            {
                "run_id": run_id,
                "x_path": "risk.fixed_lot",
                "y_path": "risk.cooldown_minutes",
                "metric": "net_profit",
            },
        )
        self.assertTrue(heatmap.payload["ok"])
        hm = heatmap.payload["heatmap"]
        self.assertEqual(2, len(hm["x_values"]))
        self.assertEqual(2, len(hm["y_values"]))
        self.assertEqual(4, len(hm["cells"]))
        self.assertTrue(
            any(cell["samples"] > 0 for cell in hm["cells"])
        )

        history = await exchange(
            reader,
            writer,
            "optimizer_history_query",
            {"limit": 20},
        )
        self.assertTrue(history.payload["ok"])
        self.assertEqual(run_id, history.payload["history"][0]["run_id"])

        journal = await exchange(
            reader,
            writer,
            "journal_query",
            {
                "date_scope": "ALL",
                "sources": ["Python Engine"],
                "search": "optimization",
                "limit": 100,
            },
        )
        self.assertTrue(journal.payload["ok"])
        tags = {
            event["tag"]
            for event in journal.payload["journal"]["events"]
        }
        self.assertIn("OPTIMIZER_START", tags)
        self.assertIn("OPTIMIZER_COMPLETE", tags)

        deleted = await exchange(
            reader,
            writer,
            "optimizer_result_delete",
            {"run_id": run_id},
        )
        self.assertTrue(deleted.payload["ok"])
        self.assertTrue(deleted.payload["deleted"])

        writer.close()
        await writer.wait_closed()

    async def test_walk_forward_result_has_train_only_leakage_evidence(self):
        reader, writer = await self.connect()
        request = self.sweep_request()
        request.update(
            {
                "folds": 3,
                "train_ratio": 0.75,
                "rolling": True,
            }
        )

        start = await exchange(
            reader,
            writer,
            "walk_forward_start",
            request,
        )
        self.assertEqual("walk_forward_start_ack", start.type)
        self.assertTrue(start.payload["ok"])
        job_id = start.payload["status"]["job_id"]

        terminal = await self.wait_for_terminal(reader, writer, job_id)
        self.assertEqual(
            "COMPLETED",
            terminal["status"],
            msg=json.dumps(terminal, sort_keys=True),
        )

        result = await exchange(
            reader,
            writer,
            "optimizer_result_get",
            {
                "run_id": terminal["result_run_id"],
                "candidate_limit": 10,
            },
        )
        self.assertTrue(result.payload["ok"])
        wf = result.payload["result"]
        self.assertEqual("WALK_FORWARD", wf["mode"])
        self.assertEqual(3, wf["fold_count"])
        self.assertTrue(wf["leakage_guard_passed"])
        self.assertGreaterEqual(wf["aggregate"]["stability"], 0.0)
        self.assertLessEqual(wf["aggregate"]["stability"], 1.0)

        for fold in wf["folds"]:
            self.assertEqual("TRAIN_ONLY", fold["selection_source"])
            self.assertTrue(fold["leakage_guard_passed"])
            self.assertLess(fold["train_to"], fold["test_from"])

        writer.close()
        await writer.wait_closed()

    async def test_background_job_keeps_heartbeat_responsive_and_cancel_works(self):
        reader, writer = await self.connect()
        original = OptimizerEngine._evaluate_candidate

        def slow(engine, index, parameters, dataset, from_date, to_date):
            time.sleep(0.08)
            return original(
                engine,
                index,
                parameters,
                dataset,
                from_date,
                to_date,
            )

        request = self.sweep_request()
        request["max_workers"] = 1
        request["parameter_ranges"] = [
            {
                "path": "risk.fixed_lot",
                "min": 0.01,
                "max": 0.20,
                "step": 0.01,
            }
        ]

        with patch.object(
            OptimizerEngine,
            "_evaluate_candidate",
            slow,
        ):
            start = await exchange(
                reader,
                writer,
                "optimizer_start",
                request,
            )
            self.assertTrue(start.payload["ok"])
            job_id = start.payload["status"]["job_id"]

            heartbeat = await exchange(reader, writer, "heartbeat")
            self.assertEqual("heartbeat_ack", heartbeat.type)
            self.assertIn(
                heartbeat.payload["optimizer_status"]["status"],
                {"QUEUED", "RUNNING"},
            )
            self.assertFalse(heartbeat.payload["execution_enabled"])

            cancel = await exchange(
                reader,
                writer,
                "optimizer_cancel",
                {"job_id": job_id},
            )
            self.assertTrue(cancel.payload["ok"])

            terminal = await self.wait_for_terminal(reader, writer, job_id)
            self.assertEqual("CANCELLED", terminal["status"])
            self.assertIsNone(terminal["result_run_id"])

        writer.close()
        await writer.wait_closed()

    async def test_engine_close_cancels_active_optimizer_without_hanging(self):
        reader, writer = await self.connect()
        original = OptimizerEngine._evaluate_candidate

        def slow(engine, index, parameters, dataset, from_date, to_date):
            time.sleep(0.15)
            return original(
                engine,
                index,
                parameters,
                dataset,
                from_date,
                to_date,
            )

        request = self.sweep_request()
        request["max_workers"] = 1
        request["parameter_ranges"] = [
            {
                "path": "risk.fixed_lot",
                "min": 0.01,
                "max": 0.20,
                "step": 0.01,
            }
        ]

        with patch.object(
            OptimizerEngine,
            "_evaluate_candidate",
            slow,
        ):
            started = await exchange(
                reader,
                writer,
                "optimizer_start",
                request,
            )
            self.assertTrue(started.payload["ok"])
            job_id = started.payload["status"]["job_id"]

            await asyncio.wait_for(
                self.server.close(),
                timeout=15,
            )

            terminal = self.server.optimizer_jobs.status(job_id)
            self.assertEqual("CANCELLED", terminal["status"])
            self.assertIsNone(terminal["result_run_id"])
            self.assertEqual(
                [],
                self.server.optimizers.history(),
            )

        writer.close()
        await writer.wait_closed()

    async def test_second_job_is_blocked_while_first_is_active(self):
        reader, writer = await self.connect()
        original = OptimizerEngine._evaluate_candidate

        def slow(engine, index, parameters, dataset, from_date, to_date):
            time.sleep(0.08)
            return original(
                engine,
                index,
                parameters,
                dataset,
                from_date,
                to_date,
            )

        request = self.sweep_request()
        request["max_workers"] = 1
        request["parameter_ranges"] = [
            {
                "path": "risk.fixed_lot",
                "min": 0.01,
                "max": 0.20,
                "step": 0.01,
            }
        ]

        with patch.object(
            OptimizerEngine,
            "_evaluate_candidate",
            slow,
        ):
            one = await exchange(
                reader,
                writer,
                "optimizer_start",
                request,
            )
            self.assertTrue(one.payload["ok"])

            two = await exchange(
                reader,
                writer,
                "optimizer_start",
                request,
            )
            self.assertFalse(two.payload["ok"])
            self.assertTrue(
                any(
                    "already active" in error
                    for error in two.payload["errors"]
                )
            )

            await exchange(
                reader,
                writer,
                "optimizer_cancel",
                {"job_id": one.payload["status"]["job_id"]},
            )
            await self.wait_for_terminal(
                reader,
                writer,
                one.payload["status"]["job_id"],
            )

        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    unittest.main()
