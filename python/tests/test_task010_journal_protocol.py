from __future__ import annotations

import asyncio
import pathlib
import sys
import tempfile
import unittest
from uuid import uuid4

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
        "bridge_version": "0.10.0-task010",
        "symbol": "XAUUSD",
        "magic": 991188,
        "terminal_connected": True,
        "account_trade_mode": "DEMO",
        "account_login": 12345678,
        "account_currency": "USD",
        "leverage": 100,
        "balance": 10000.0,
        "equity": 10010.0,
        "margin_free": 9950.0,
        "bid": 4281.10,
        "ask": 4281.35,
        "spread_points": 25.0,
        "digits": 2,
        "point": 0.01,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "stops_level": 10,
        "freeze_level": 5,
        "positions_count": 1,
        "orders_count": 0,
        "own_daily_realized": 0.0,
        "positions": [
            {
                "ticket": 32874561,
                "magic": 991188,
                "symbol": "XAUUSD",
                "side": "BUY",
                "volume": 0.10,
                "price_open": 4280.0,
                "price_current": 4281.1,
                "sl": 4275.0,
                "tp": 4290.0,
                "profit": 11.0,
                "swap": 0.0,
                "time": 1790239000,
                "comment": "XAUPY",
            }
        ],
        "orders": [],
        "deals": [],
        "guardian": {
            "execution_locked": True,
            "execution_ready": False,
            "reason": "TASK003_EXECUTION_LOCKED",
            "daily_realized": 0.0,
            "daily_loss_limit": 200.0,
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


class Task010JournalProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = EngineServer(
            port=0,
            journal_dir=self.temp.name,
            bridge_stale_seconds=1.0,
        )
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.close()
        self.temp.cleanup()

    async def connect(self):
        return await asyncio.open_connection(
            "127.0.0.1",
            self.server.bound_port,
        )

    async def test_heartbeat_includes_compact_real_journal_summary(self):
        reader, writer = await self.connect()
        heartbeat = await exchange(reader, writer, "heartbeat")
        summary = heartbeat.payload["journal_summary"]

        self.assertEqual(1, summary["schema_version"])
        self.assertGreaterEqual(summary["total"], 1)
        self.assertGreaterEqual(summary["level_counts"]["INFO"], 1)
        self.assertFalse(heartbeat.payload["trading_enabled"])
        self.assertFalse(heartbeat.payload["execution_enabled"])

        writer.close()
        await writer.wait_closed()

    async def test_bridge_strategy_and_manual_action_are_queryable(self):
        reader, writer = await self.connect()

        hello = await exchange(
            reader,
            writer,
            "bridge_hello",
            {
                "bridge_version": "0.10.0-task010",
                "symbol": "XAUUSD",
                "magic": 991188,
                "execution_locked": True,
            },
        )
        self.assertEqual("bridge_hello_ack", hello.type)

        snapshot = await exchange(
            reader,
            writer,
            "bridge_snapshot",
            bridge_snapshot(),
        )
        self.assertEqual("bridge_snapshot_ack", snapshot.type)

        manual = await exchange(
            reader,
            writer,
            "manual_action_simulate",
            {
                "intent_id": str(uuid4()),
                "action": "CLOSE_POSITION",
                "confirmed": True,
                "ticket": 32874561,
            },
        )
        self.assertEqual("manual_action_simulate_ack", manual.type)
        self.assertTrue(manual.payload["accepted"])
        self.assertFalse(manual.payload["broker_mutated"])

        journal = await exchange(
            reader,
            writer,
            "journal_query",
            {
                "date_scope": "ALL",
                "limit": 500,
            },
        )
        self.assertEqual("journal_query_ack", journal.type)
        self.assertTrue(journal.payload["ok"])

        events = journal.payload["journal"]["events"]
        sources = {event["source"] for event in events}
        tags = {event["tag"] for event in events}

        self.assertIn("EA Bridge", sources)
        self.assertIn("MT5", sources)
        self.assertIn("Strategy", sources)
        self.assertIn("Orders", sources)
        self.assertIn("DECISION_TRACE", tags)
        self.assertIn("ORDER", tags)

        order_event = next(
            event
            for event in events
            if event["source"] == "Orders"
            and event["tag"] == "ORDER"
        )
        self.assertIsNotNone(order_event["correlation_id"])
        self.assertEqual(
            "CLOSE_POSITION",
            order_event["details"]["request"]["action"],
        )

        writer.close()
        await writer.wait_closed()

    async def test_query_filters_and_persisted_bookmark_protocol(self):
        reader, writer = await self.connect()

        initial = await exchange(
            reader,
            writer,
            "journal_query",
            {
                "sources": ["Python Engine"],
                "levels": ["INFO", "DEBUG"],
                "search": "IPC",
                "date_scope": "ALL",
                "limit": 100,
            },
        )
        self.assertTrue(initial.payload["ok"])
        events = initial.payload["journal"]["events"]
        self.assertGreaterEqual(len(events), 1)

        sequence = events[0]["sequence"]
        bookmarked = await exchange(
            reader,
            writer,
            "journal_bookmark_set",
            {
                "sequence": sequence,
                "bookmarked": True,
            },
        )
        self.assertTrue(bookmarked.payload["ok"])
        self.assertTrue(bookmarked.payload["event"]["bookmarked"])

        bookmarks_only = await exchange(
            reader,
            writer,
            "journal_query",
            {
                "date_scope": "ALL",
                "bookmarks_only": True,
                "limit": 100,
            },
        )
        self.assertTrue(bookmarks_only.payload["ok"])
        self.assertEqual(
            sequence,
            bookmarks_only.payload["journal"]["events"][0]["sequence"],
        )

        writer.close()
        await writer.wait_closed()

    async def test_invalid_query_is_rejected_without_enabling_execution(self):
        reader, writer = await self.connect()

        response = await exchange(
            reader,
            writer,
            "journal_query",
            {
                "levels": ["TRACE"],
                "date_scope": "ALL",
            },
        )
        self.assertEqual("journal_query_ack", response.type)
        self.assertFalse(response.payload["ok"])
        self.assertGreaterEqual(len(response.payload["errors"]), 1)
        self.assertFalse(response.payload["trading_enabled"])
        self.assertFalse(response.payload["execution_enabled"])

        writer.close()
        await writer.wait_closed()

    async def test_restart_replays_events_and_bookmarks(self):
        reader, writer = await self.connect()
        queried = await exchange(
            reader,
            writer,
            "journal_query",
            {"date_scope": "ALL", "limit": 100},
        )
        target = queried.payload["journal"]["events"][0]
        await exchange(
            reader,
            writer,
            "journal_bookmark_set",
            {
                "sequence": target["sequence"],
                "bookmarked": True,
            },
        )
        writer.close()
        await writer.wait_closed()

        await self.server.close()

        replayed = EngineServer(
            port=0,
            journal_dir=self.temp.name,
            bridge_stale_seconds=1.0,
        )
        await replayed.start()
        try:
            r2, w2 = await asyncio.open_connection(
                "127.0.0.1",
                replayed.bound_port,
            )
            result = await exchange(
                r2,
                w2,
                "journal_query",
                {
                    "date_scope": "ALL",
                    "bookmarks_only": True,
                    "limit": 100,
                },
            )
            self.assertTrue(result.payload["ok"])
            events = result.payload["journal"]["events"]
            self.assertTrue(
                any(
                    event["sequence"] == target["sequence"]
                    and event["bookmarked"]
                    for event in events
                )
            )
            self.assertGreater(
                result.payload["journal"]["latest_sequence"],
                target["sequence"],
            )
            w2.close()
            await w2.wait_closed()
        finally:
            await replayed.close()

        # Prevent asyncTearDown from closing the old already-closed server twice.
        self.server = replayed


if __name__ == "__main__":
    unittest.main()
