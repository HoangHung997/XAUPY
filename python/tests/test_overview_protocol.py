import asyncio
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.contracts import Envelope
from xaupy_engine.server import EngineServer


TIMEFRAMES = ("M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4")


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
        "account_currency": "USD",
        "balance": 10000.0,
        "equity": 10025.0,
        "margin_free": 9900.0,
        "bid": 4281.10,
        "ask": 4281.35,
        "spread_points": 25.0,
        "positions_count": 0,
        "orders_count": 0,
        "guardian": {
            "execution_locked": True,
            "execution_ready": False,
            "reason": "TASK003_EXECUTION_LOCKED",
        },
        "bars": {tf: dict(bar) for tf in TIMEFRAMES},
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


class OverviewProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = EngineServer(port=0)
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.close()

    async def connect(self):
        return await asyncio.open_connection("127.0.0.1", self.server.bound_port)

    async def test_desktop_heartbeat_contains_overview_projection(self):
        bridge_reader, bridge_writer = await self.connect()
        await exchange(
            bridge_reader,
            bridge_writer,
            "bridge_hello",
            {"bridge_version": "0.3.0-task003", "symbol": "XAUUSD"},
        )
        await exchange(
            bridge_reader,
            bridge_writer,
            "bridge_snapshot",
            bridge_snapshot(),
        )

        desktop_reader, desktop_writer = await self.connect()
        response = await exchange(desktop_reader, desktop_writer, "heartbeat")

        self.assertEqual("heartbeat_ack", response.type)
        self.assertIn("overview", response.payload)
        overview = response.payload["overview"]
        self.assertTrue(overview["available"])
        self.assertEqual("XAUUSD", overview["symbol"])
        self.assertEqual(4281.10, overview["bid"])
        self.assertEqual("USD", overview["account_currency"])
        self.assertFalse(response.payload["execution_enabled"])
        self.assertFalse(response.payload["trading_enabled"])

        bridge_writer.close()
        desktop_writer.close()
        await bridge_writer.wait_closed()
        await desktop_writer.wait_closed()


if __name__ == "__main__":
    unittest.main()
