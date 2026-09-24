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


class EngineServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = EngineServer(port=0)
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.close()

    async def _connect(self):
        return await asyncio.open_connection("127.0.0.1", self.server.bound_port)

    async def test_hello_and_heartbeat_never_enable_trading(self):
        reader, writer = await self._connect()
        hello = await exchange(reader, writer, "hello", {"component": "test"})
        self.assertEqual("hello_ack", hello.type)
        self.assertFalse(hello.payload["trading_enabled"])

        heartbeat = await exchange(reader, writer, "heartbeat")
        self.assertEqual("heartbeat_ack", heartbeat.type)
        self.assertFalse(heartbeat.payload["trading_enabled"])
        self.assertGreaterEqual(heartbeat.payload["connections_total"], 1)

        writer.close()
        await writer.wait_closed()

    async def test_client_can_disconnect_and_reconnect(self):
        reader1, writer1 = await self._connect()
        await exchange(reader1, writer1, "hello")
        writer1.close()
        await writer1.wait_closed()

        reader2, writer2 = await self._connect()
        heartbeat = await exchange(reader2, writer2, "heartbeat")
        self.assertEqual("heartbeat_ack", heartbeat.type)
        self.assertGreaterEqual(heartbeat.payload["connections_total"], 2)

        writer2.close()
        await writer2.wait_closed()

    async def test_shutdown_ack_sets_shutdown_event(self):
        reader, writer = await self._connect()
        response = await exchange(reader, writer, "shutdown")
        self.assertEqual("shutdown_ack", response.type)
        await asyncio.wait_for(self.server.wait_for_shutdown(), timeout=2)

        writer.close()
        await writer.wait_closed()

    async def test_unsupported_message_returns_error(self):
        reader, writer = await self._connect()
        response = await exchange(reader, writer, "place_order", {"symbol": "XAUUSD"})
        self.assertEqual("error", response.type)
        self.assertEqual("UNSUPPORTED_MESSAGE", response.payload["code"])
        self.assertFalse(response.payload["trading_enabled"])

        writer.close()
        await writer.wait_closed()

    async def test_non_loopback_bind_is_rejected(self):
        with self.assertRaises(ValueError):
            EngineServer(host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
