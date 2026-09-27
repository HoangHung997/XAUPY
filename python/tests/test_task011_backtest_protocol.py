from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.config_schema import default_profile
from xaupy_engine.contracts import Envelope
from xaupy_engine.server import EngineServer


def profile_for_backtest():
    profile = default_profile()
    profile["profile"]["name"] = "Task011 IPC Test"
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
    profile["risk"]["max_lot"] = 0.10
    profile["risk"]["cooldown_minutes"] = 0
    profile["risk"]["max_consecutive_losses"] = 8
    profile["risk"]["max_daily_loss_pct"] = 50.0
    profile["stop_loss"]["mode"] = "FIXED"
    profile["stop_loss"]["fixed_price_units"] = 2.0
    profile["take_profit"]["mode"] = "FIXED"
    profile["take_profit"]["fixed_price_units"] = 3.0
    profile["management"]["breakeven_enabled"] = False
    profile["management"]["partial_close_enabled"] = False
    profile["management"]["trailing_enabled"] = False
    profile["management"]["sl_tighten_mode"] = "OFF"
    profile["sessions"]["timezone"] = "UTC"
    profile["sessions"]["session1_enabled"] = False
    profile["sessions"]["session2_enabled"] = False
    profile["news"]["enabled"] = False
    return profile


def write_dataset(path: pathlib.Path):
    start = 1_704_067_200
    closes = [100.0, 99.0, 98.0, 97.0, 100.0, 102.0, 101.0, 102.0]
    bars = []
    previous = closes[0]
    for index, close in enumerate(closes):
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
                "time": start + index * 60,
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
    line = await asyncio.wait_for(reader.readline(), timeout=8)
    response = Envelope.from_json(line.decode("utf-8").rstrip("\r\n"))
    if response.request_id != request.request_id:
        raise AssertionError("response request_id mismatch")
    return response


class Task011BacktestProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dataset_path = pathlib.Path(self.temp.name, "history.json")
        self.journal_dir = pathlib.Path(self.temp.name, "journal")
        self.backtest_dir = pathlib.Path(self.temp.name, "backtests")
        write_dataset(self.dataset_path)

        self.server = EngineServer(
            port=0,
            journal_dir=self.journal_dir,
            backtest_dir=self.backtest_dir,
        )
        self.server.active_profile = profile_for_backtest()
        self.server.strategy.set_profile(self.server.active_profile)
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.close()
        self.temp.cleanup()

    async def connect(self):
        return await asyncio.open_connection(
            "127.0.0.1",
            self.server.bound_port,
        )

    async def test_inspect_run_history_get_delete_roundtrip(self):
        reader, writer = await self.connect()

        inspect = await exchange(
            reader,
            writer,
            "backtest_dataset_inspect",
            {"path": str(self.dataset_path)},
        )
        self.assertEqual("backtest_dataset_inspect_ack", inspect.type)
        self.assertTrue(inspect.payload["ok"])
        self.assertEqual("XAUUSD", inspect.payload["dataset"]["metadata"]["symbol"])
        self.assertEqual(8, inspect.payload["dataset"]["bar_count"])
        self.assertFalse(inspect.payload["trading_enabled"])
        self.assertFalse(inspect.payload["execution_enabled"])

        run = await exchange(
            reader,
            writer,
            "backtest_run",
            {
                "path": str(self.dataset_path),
                "from_date": "2024-01-01",
                "to_date": "2024-01-01",
                "initial_balance": 10000.0,
                "spread_pips": 0.0,
                "commission_per_lot": 7.0,
            },
        )
        self.assertEqual("backtest_run_ack", run.type)
        self.assertTrue(run.payload["ok"])
        result = run.payload["result"]
        self.assertEqual("M1_OHLC_PARITY_V1", result["model"])
        self.assertEqual(64, len(result["result_hash"]))
        self.assertGreaterEqual(result["trade_total"], 1)
        self.assertEqual(result["metrics"]["total_trades"], result["trade_total"])
        self.assertFalse(run.payload["trading_enabled"])
        self.assertFalse(run.payload["execution_enabled"])

        run_id = result["run_id"]

        history = await exchange(
            reader,
            writer,
            "backtest_history_query",
            {"limit": 20},
        )
        self.assertTrue(history.payload["ok"])
        self.assertEqual(run_id, history.payload["history"][0]["run_id"])

        fetched = await exchange(
            reader,
            writer,
            "backtest_result_get",
            {
                "run_id": run_id,
                "trade_offset": 0,
                "trade_limit": 1,
            },
        )
        self.assertTrue(fetched.payload["ok"])
        self.assertEqual(1, len(fetched.payload["result"]["trades"]))
        self.assertEqual(result["result_hash"], fetched.payload["result"]["result_hash"])

        deleted = await exchange(
            reader,
            writer,
            "backtest_result_delete",
            {"run_id": run_id},
        )
        self.assertTrue(deleted.payload["ok"])
        self.assertTrue(deleted.payload["deleted"])

        history_after = await exchange(
            reader,
            writer,
            "backtest_history_query",
            {"limit": 20},
        )
        self.assertEqual([], history_after.payload["history"])

        writer.close()
        await writer.wait_closed()

    async def test_repeat_run_has_same_deterministic_result_hash(self):
        reader, writer = await self.connect()
        payload = {
            "path": str(self.dataset_path),
            "from_date": "2024-01-01",
            "to_date": "2024-01-01",
            "initial_balance": 10000.0,
            "spread_pips": 0.0,
            "commission_per_lot": 7.0,
        }
        one = await exchange(reader, writer, "backtest_run", payload)
        two = await exchange(reader, writer, "backtest_run", payload)

        self.assertTrue(one.payload["ok"])
        self.assertTrue(two.payload["ok"])
        self.assertNotEqual(
            one.payload["result"]["run_id"],
            two.payload["result"]["run_id"],
        )
        self.assertEqual(
            one.payload["result"]["result_hash"],
            two.payload["result"]["result_hash"],
        )
        self.assertEqual(
            one.payload["result"]["trades"],
            two.payload["result"]["trades"],
        )

        writer.close()
        await writer.wait_closed()

    async def test_backtest_evidence_is_written_to_task010_journal(self):
        reader, writer = await self.connect()

        await exchange(
            reader,
            writer,
            "backtest_dataset_inspect",
            {"path": str(self.dataset_path)},
        )
        await exchange(
            reader,
            writer,
            "backtest_run",
            {
                "path": str(self.dataset_path),
                "from_date": "2024-01-01",
                "to_date": "2024-01-01",
                "initial_balance": 10000.0,
                "spread_pips": 0.0,
                "commission_per_lot": 0.0,
            },
        )

        journal = await exchange(
            reader,
            writer,
            "journal_query",
            {
                "date_scope": "ALL",
                "sources": ["Python Engine"],
                "search": "Backtest",
                "limit": 100,
            },
        )
        self.assertTrue(journal.payload["ok"])
        tags = {
            event["tag"]
            for event in journal.payload["journal"]["events"]
        }
        self.assertIn("BACKTEST_DATASET", tags)
        self.assertIn("BACKTEST_RUN", tags)

        completed = next(
            event
            for event in journal.payload["journal"]["events"]
            if event["tag"] == "BACKTEST_RUN"
            and event["message"] == "Backtest completed"
        )
        self.assertEqual(64, len(completed["details"]["result_hash"]))
        self.assertIn("metrics", completed["details"])

        writer.close()
        await writer.wait_closed()

    async def test_profile_requiring_missing_historical_news_is_rejected_without_execution(self):
        profile = profile_for_backtest()
        profile["news"]["enabled"] = True
        self.server.active_profile = deepcopy(profile)
        self.server.strategy.set_profile(profile)

        reader, writer = await self.connect()
        response = await exchange(
            reader,
            writer,
            "backtest_run",
            {
                "path": str(self.dataset_path),
                "from_date": "2024-01-01",
                "to_date": "2024-01-01",
            },
        )

        self.assertEqual("backtest_run_ack", response.type)
        self.assertFalse(response.payload["ok"])
        self.assertTrue(
            any(
                "news.enabled" in error
                for error in response.payload["errors"]
            )
        )
        self.assertFalse(response.payload["trading_enabled"])
        self.assertFalse(response.payload["execution_enabled"])

        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    unittest.main()
