import asyncio
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.contracts import Envelope
from xaupy_engine.server import EngineServer


def bridge_snapshot():
    bar = {
        "time": 1790240000,
        "open": 4280.0,
        "high": 4282.0,
        "low": 4279.0,
        "close": 4281.0,
        "tick_volume": 123,
    }
    return {
        "bridge_version": "0.3.0-task003",
        "symbol": "XAUUSD",
        "terminal_connected": True,
        "account_trade_mode": "DEMO",
        "bid": 4281.10,
        "ask": 4281.35,
        "guardian": {
            "execution_locked": True,
            "execution_ready": False,
            "reason": "TASK003_EXECUTION_LOCKED",
        },
        "bars": {tf: dict(bar) for tf in ("M1","M3","M5","M15","M30","H1","H2","H4")},
    }


async def exchange(reader, writer, message_type, payload=None):
    request = Envelope.create(message_type, payload or {})
    writer.write((request.to_json() + "\n").encode("utf-8"))
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=2)
    response = Envelope.from_json(line.decode("utf-8").rstrip("\r\n"))
    if response.request_id != request.request_id:
        raise AssertionError("response request_id mismatch")
    return response


class BridgeProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = EngineServer(port=0, bridge_stale_seconds=0.05)
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.close()

    async def connect(self):
        return await asyncio.open_connection("127.0.0.1", self.server.bound_port)

    async def test_bridge_snapshot_is_projected_into_desktop_heartbeat(self):
        bridge_reader, bridge_writer = await self.connect()

        hello = await exchange(
            bridge_reader,
            bridge_writer,
            "bridge_hello",
            {"bridge_version": "0.3.0-task003", "symbol": "XAUUSD"},
        )
        self.assertEqual("bridge_hello_ack", hello.type)
        self.assertFalse(hello.payload["execution_enabled"])

        snap = await exchange(
            bridge_reader,
            bridge_writer,
            "bridge_snapshot",
            bridge_snapshot(),
        )
        self.assertEqual("bridge_snapshot_ack", snap.type)
        self.assertIsNone(snap.payload["command"])
        self.assertFalse(snap.payload["execution_enabled"])

        desktop_reader, desktop_writer = await self.connect()
        heartbeat = await exchange(desktop_reader, desktop_writer, "heartbeat")
        bridge = heartbeat.payload["bridge"]

        self.assertTrue(bridge["connected"])
        self.assertEqual("XAUUSD", bridge["symbol"])
        self.assertEqual("DEMO", bridge["account_trade_mode"])
        self.assertTrue(bridge["execution_locked"])
        self.assertFalse(bridge["execution_ready"])
        self.assertEqual(1, bridge["snapshots_total"])

        bridge_writer.close()
        desktop_writer.close()
        await bridge_writer.wait_closed()
        await desktop_writer.wait_closed()

    async def test_stale_bridge_is_reported_offline(self):
        reader, writer = await self.connect()
        await exchange(reader, writer, "bridge_snapshot", bridge_snapshot())
        await asyncio.sleep(0.08)

        heartbeat = await exchange(reader, writer, "heartbeat")
        self.assertFalse(heartbeat.payload["bridge"]["connected"])

        writer.close()
        await writer.wait_closed()

    async def test_trade_intent_remains_unsupported(self):
        reader, writer = await self.connect()
        response = await exchange(
            reader,
            writer,
            "trade_intent",
            {"symbol": "XAUUSD", "side": "SELL", "volume": 0.1},
        )
        self.assertEqual("error", response.type)
        self.assertEqual("UNSUPPORTED_MESSAGE", response.payload["code"])
        self.assertFalse(response.payload["execution_enabled"])
        self.assertFalse(response.payload["trading_enabled"])

        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    unittest.main()
