import asyncio
import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.contracts import Envelope
from xaupy_engine.server import EngineServer


async def exchange(reader, writer, message_type, payload=None):
    request = Envelope.create(message_type, payload or {})
    writer.write((request.to_json() + "\n").encode("utf-8"))
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=2)
    response = Envelope.from_json(line.decode("utf-8").rstrip("\r\n"))
    if response.request_id != request.request_id:
        raise AssertionError("response request_id mismatch")
    return response


class ActiveConfigProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = EngineServer(port=0)
        await self.server.start()
        self.reader, self.writer = await asyncio.open_connection(
            "127.0.0.1", self.server.bound_port
        )

    async def asyncTearDown(self):
        self.writer.close()
        await self.writer.wait_closed()
        await self.server.close()

    async def test_active_profile_starts_from_defaults(self):
        defaults = await exchange(self.reader, self.writer, "config_defaults_get")
        active = await exchange(self.reader, self.writer, "config_active_get")

        self.assertEqual(defaults.payload["profile"], active.payload["profile"])
        self.assertFalse(active.payload["execution_enabled"])
        self.assertFalse(active.payload["trading_enabled"])

    async def test_apply_updates_active_profile(self):
        defaults = await exchange(self.reader, self.writer, "config_defaults_get")
        profile = copy.deepcopy(defaults.payload["profile"])
        profile["profile"]["name"] = "Task006 Test"
        profile["timeframes"]["direction"] = "H1"
        profile["timeframes"]["pullback"] = "M15"
        profile["timeframes"]["trigger"] = "M3"
        profile["pullback"]["rsi_buy_level"] = "45"
        profile["pullback"]["rsi_sell_level"] = "55"

        applied = await exchange(
            self.reader,
            self.writer,
            "config_active_set",
            {"profile": profile},
        )

        self.assertEqual("config_active_set_ack", applied.type)
        self.assertTrue(applied.payload["applied"])
        self.assertEqual([], applied.payload["errors"])
        self.assertEqual("H1", applied.payload["profile"]["timeframes"]["direction"])
        self.assertEqual(45.0, applied.payload["profile"]["pullback"]["rsi_buy_level"])
        self.assertFalse(applied.payload["execution_enabled"])

        active = await exchange(self.reader, self.writer, "config_active_get")
        self.assertEqual("Task006 Test", active.payload["profile"]["profile"]["name"])
        self.assertEqual("M15", active.payload["profile"]["timeframes"]["pullback"])
        self.assertEqual("M3", active.payload["profile"]["timeframes"]["trigger"])

    async def test_invalid_apply_does_not_replace_active(self):
        original = await exchange(self.reader, self.writer, "config_active_get")
        invalid = copy.deepcopy(original.payload["profile"])
        invalid["execution"]["allow_real_account"] = True

        result = await exchange(
            self.reader,
            self.writer,
            "config_active_set",
            {"profile": invalid},
        )

        self.assertFalse(result.payload["applied"])
        self.assertTrue(
            any("allow_real_account" in error for error in result.payload["errors"])
        )

        active = await exchange(self.reader, self.writer, "config_active_get")
        self.assertEqual(original.payload["profile"], active.payload["profile"])

    async def test_unusual_timeframe_order_can_be_active(self):
        active = await exchange(self.reader, self.writer, "config_active_get")
        profile = copy.deepcopy(active.payload["profile"])
        profile["timeframes"] = {
            "direction": "M1",
            "pullback": "H4",
            "trigger": "M3",
        }

        result = await exchange(
            self.reader,
            self.writer,
            "config_active_set",
            {"profile": profile},
        )
        self.assertTrue(result.payload["applied"])
        self.assertEqual(
            {"direction": "M1", "pullback": "H4", "trigger": "M3"},
            result.payload["profile"]["timeframes"],
        )


if __name__ == "__main__":
    unittest.main()
