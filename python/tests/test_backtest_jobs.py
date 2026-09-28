import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import time
from threading import Event
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xaupy_engine.backtest import BacktestCancelled
from xaupy_engine.server import EngineServer
from xaupy_engine.demo_once import profile_hash
from test_task011_backtest_protocol import exchange, profile_for_backtest, write_dataset


class BacktestJobProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="xaupy-backtest-jobs-")
        self.path = Path(self.temp.name) / "bars.json"
        write_dataset(self.path)
        self.server = EngineServer(port=0, state_dir=Path(self.temp.name) / "state")
        self.server.active_profile = profile_for_backtest()
        await self.server.start()
        self.reader, self.writer = await asyncio.open_connection("127.0.0.1", self.server.bound_port)

    async def asyncTearDown(self):
        self.writer.close()
        await self.writer.wait_closed()
        await self.server.close()
        self.temp.cleanup()

    async def request(self, kind, payload=None):
        return await exchange(self.reader, self.writer, kind, payload)

    async def start_job(self):
        response = await self.request("backtest_start", {"path": str(self.path), "from_date": "2024-01-01", "to_date": "2024-01-01", "spread_pips": 0})
        self.assertTrue(response.payload["ok"])
        return response.payload["job"]["job_id"]

    async def wait_done(self, job_id):
        for _ in range(200):
            response = await self.request("backtest_status", {"job_id": job_id})
            job = response.payload["job"]
            if job["state"] not in {"QUEUED", "RUNNING", "CANCELLING"}:
                return job
            await asyncio.sleep(.01)
        self.fail("Job did not finish")

    async def test_heartbeat_and_cancellation_work_while_replay_is_busy(self):
        entered = Event()
        def slow_replay(engine, *args, cancel_check=None, **kwargs):
            entered.set()
            for _ in range(500):
                if cancel_check():
                    raise BacktestCancelled()
                time.sleep(.01)
            raise AssertionError("Cancellation did not reach replay")
        with patch("xaupy_engine.backtest_jobs.BacktestEngine.run", slow_replay):
            job_id = await self.start_job()
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            heartbeat = await asyncio.wait_for(self.request("heartbeat"), .75)
            self.assertEqual("heartbeat_ack", heartbeat.type)
            cancelled = await self.request("backtest_cancel", {"job_id": job_id})
            self.assertTrue(cancelled.payload["ok"])
            self.assertEqual("CANCELLED", (await self.wait_done(job_id))["state"])
            self.assertEqual([], self.server.backtests.history())

    async def test_profile_is_frozen_and_completed_result_is_saved(self):
        original = deepcopy(self.server.active_profile)
        job_id = await self.start_job()
        self.server.active_profile["profile"]["name"] = "Changed after start"
        job = await self.wait_done(job_id)
        self.assertEqual("COMPLETED", job["state"], job)
        saved = self.server.backtests.get(job["run_id"])
        self.assertEqual(profile_hash(original), saved["engine_profile_hash"])
        self.assertEqual(job["total_bars"], job["completed_bars"])
        self.assertGreater(job["total_bars"], 0)

    async def test_invalid_job_is_an_error_and_does_not_break_connection(self):
        response = await self.request("backtest_cancel", {"job_id": "missing"})
        self.assertFalse(response.payload["ok"])
        self.assertEqual("heartbeat_ack", (await self.request("heartbeat")).type)

    async def test_config_compare_and_swap_preserves_other_editor_changes(self):
        baseline = deepcopy(self.server.active_profile)
        draft = deepcopy(baseline)
        draft["profile"]["name"] = "Tools draft"
        other = deepcopy(baseline)
        other["strategy"]["symbol"] = "EURUSD"
        self.server.active_profile = other
        rejected = await self.request("config_active_set", {"profile": draft, "expected_profile": baseline})
        self.assertFalse(rejected.payload["applied"])
        self.assertEqual(other, self.server.active_profile)
        accepted = await self.request("config_active_set", {"profile": draft, "expected_profile": other})
        self.assertTrue(accepted.payload["applied"])
        self.assertEqual("Tools draft", self.server.active_profile["profile"]["name"])


if __name__ == "__main__":
    unittest.main()
