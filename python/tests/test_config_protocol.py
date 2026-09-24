import asyncio
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


class ConfigProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = EngineServer(port=0)
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.close()

    async def connect(self):
        return await asyncio.open_connection("127.0.0.1", self.server.bound_port)

    async def test_schema_contains_exact_timeframe_options_and_many_fields(self):
        reader, writer = await self.connect()
        response = await exchange(reader, writer, "config_schema_get")
        self.assertEqual("config_schema_ack", response.type)
        schema = response.payload["config_schema"]
        self.assertEqual(
            ["M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4"],
            schema["timeframe_options"],
        )
        self.assertGreaterEqual(schema["field_count"], 100)
        self.assertFalse(response.payload["execution_enabled"])
        writer.close()
        await writer.wait_closed()

    async def test_defaults_are_valid(self):
        reader, writer = await self.connect()
        defaults = await exchange(reader, writer, "config_defaults_get")
        profile = defaults.payload["profile"]

        validated = await exchange(
            reader,
            writer,
            "config_validate",
            {"profile": profile},
        )
        self.assertEqual("config_validate_ack", validated.type)
        self.assertTrue(validated.payload["valid"])
        self.assertEqual([], validated.payload["errors"])
        self.assertFalse(validated.payload["execution_enabled"])
        writer.close()
        await writer.wait_closed()

    async def test_live_unlock_attempt_is_rejected(self):
        reader, writer = await self.connect()
        defaults = await exchange(reader, writer, "config_defaults_get")
        profile = defaults.payload["profile"]
        profile["execution"]["allow_real_account"] = True

        validated = await exchange(
            reader,
            writer,
            "config_validate",
            {"profile": profile},
        )
        self.assertFalse(validated.payload["valid"])
        self.assertTrue(
            any("allow_real_account" in error for error in validated.payload["errors"])
        )
        self.assertFalse(validated.payload["execution_enabled"])
        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    unittest.main()
