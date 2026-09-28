from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from xaupy_engine.bridge_state import BridgeRegistry, BridgeSnapshotError
from xaupy_engine.config_schema import default_profile
from xaupy_engine.contracts import Envelope
from xaupy_engine.server import EngineServer, MAX_LINE_BYTES
from xaupy_engine.strategy_engine import (
    HISTORY_TIMEFRAME_SECONDS, StrategyDataError, StrategyEngine, validated_bar_history,
)


def history_snapshot(count=256):
    now = 1_704_067_200 + 256 * 14400
    history = {}
    for tf, seconds in HISTORY_TIMEFRAME_SECONDS.items():
        end = now // seconds * seconds
        history[tf] = [
            {"time": end - (count - i) * seconds,
             "open": 2000 + i * 0.1, "high": 2001 + i * 0.1,
             "low": 1999 + i * 0.1, "close": 2000.5 + i * 0.1,
             "tick_volume": 100 + i}
            for i in range(count)
        ]
    return {
        "bridge_version": "0.14.0", "symbol": "XAUUSD",
        "terminal_connected": True, "account_trade_mode": "DEMO",
        "bid": 2026.1, "ask": 2026.3, "server_time": now,
        "guardian": {"execution_locked": True, "execution_ready": False},
        "bars": {tf: deepcopy(rows[-1]) for tf, rows in history.items()},
        "bar_history": history,
    }


class BridgeHistoryTests(unittest.TestCase):
    def test_history_bootstrap_warms_indicators_without_replaying_signals(self):
        strategy = StrategyEngine()
        payload = history_snapshot()
        status = strategy.ingest_snapshot(payload)
        self.assertEqual({tf: 256 for tf in HISTORY_TIMEFRAME_SECONDS}, status["bars_seen"])
        self.assertNotEqual("WARMUP", status["state"])
        self.assertEqual(0, status["signal_sequence"])
        self.assertIsNone(status["last_signal"])
        self.assertEqual("HISTORY_BOOTSTRAP", status["last_reset_reason"])
        self.assertIsNotNone(status["indicators"]["direction"]["ma"])
        again = strategy.ingest_snapshot(payload)
        self.assertEqual(1, again["history_bootstrap_total"])
        self.assertEqual(0, again["signal_sequence"])

    def test_bootstrap_reconnect_gap_resets_setup_without_historical_entry(self):
        strategy = StrategyEngine()
        payload = history_snapshot(10)
        strategy.ingest_snapshot(payload)
        strategy.armed_side = "BUY"
        strategy._armed_trigger_time = payload["bars"]["M1"]["time"]
        later = history_snapshot(256)
        for tf, rows in later["bar_history"].items():
            for row in rows:
                row["time"] += 14400
            later["bars"][tf] = deepcopy(rows[-1])
        later["server_time"] += 14400
        status = strategy.ingest_snapshot(later)
        self.assertEqual(2, status["history_bootstrap_total"])
        self.assertIsNone(status["last_signal"])
        self.assertEqual(0, status["signal_sequence"])

    def test_repeated_history_does_not_consume_next_live_bar(self):
        strategy = StrategyEngine()
        payload = history_snapshot()
        strategy.ingest_snapshot(payload)
        next_payload = deepcopy(payload)
        next_payload["server_time"] += 60
        new_bar = deepcopy(payload["bars"]["M1"])
        new_bar["time"] += 60
        next_payload["bars"]["M1"] = new_bar
        next_payload["bar_history"]["M1"] = payload["bar_history"]["M1"][1:] + [new_bar]
        status = strategy.ingest_snapshot(next_payload)
        self.assertEqual(257, status["bars_seen"]["M1"])
        self.assertEqual(1, status["history_bootstrap_total"])
        self.assertEqual(new_bar["time"], strategy.history["M1"][-1].time)

    def test_history_validation_is_atomic_for_bad_order_future_and_oversize(self):
        valid = history_snapshot()
        mutations = (
            lambda p: p["bar_history"]["M1"].reverse(),
            lambda p: p["bar_history"]["M1"].append(deepcopy(p["bar_history"]["M1"][-1])),
            lambda p: p.__setitem__("server_time", p["server_time"] - 60),
            lambda p: p["bar_history"]["M1"][0].__setitem__("high", 0),
            lambda p: p["bar_history"].__setitem__("W1", []),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                registry = BridgeRegistry()
                registry.record_snapshot(valid)
                before = registry.overview_payload()
                invalid = deepcopy(valid)
                mutate(invalid)
                with self.assertRaises(BridgeSnapshotError):
                    registry.record_snapshot(invalid)
                self.assertEqual(before, registry.overview_payload())
                strategy = StrategyEngine()
                with self.assertRaises(StrategyDataError):
                    strategy.ingest_snapshot(invalid)
                self.assertFalse(any(strategy.history.values()))

    def test_history_retained_on_ordinary_snapshots_and_bounded(self):
        registry = BridgeRegistry()
        payload = history_snapshot()
        registry.record_snapshot(payload)
        ordinary = deepcopy(payload)
        del ordinary["bar_history"]
        ordinary["server_time"] += 60
        ordinary["bars"]["M1"]["time"] += 60
        registry.record_snapshot(ordinary)
        overview = registry.overview_payload()
        self.assertEqual(256, len(overview["bar_history"]["M1"]))
        self.assertEqual(ordinary["bars"]["M1"], overview["bar_history"]["M1"][-1])
        self.assertEqual(payload["bar_history"]["M30"], overview["bar_history"]["M30"])
        self.assertEqual(payload["bar_history"]["D1"], overview["bar_history"]["D1"])

    def test_symbol_switch_clears_previous_symbol_history(self):
        payload = history_snapshot()
        registry = BridgeRegistry()
        registry.record_snapshot(payload)
        changed = deepcopy(payload)
        changed["symbol"] = "XAUUSD.a"
        del changed["bar_history"]
        registry.record_snapshot(changed)
        self.assertEqual(1, len(registry.overview_payload()["bar_history"]["M1"]))
        strategy = StrategyEngine()
        strategy.ingest_snapshot(payload)
        profile = default_profile()
        profile["strategy"]["symbol"] = "XAUUSD.a"
        strategy.set_profile(profile)
        self.assertFalse(any(strategy.history.values()))

    def test_legacy_snapshot_needs_no_server_time_or_history(self):
        payload = history_snapshot()
        del payload["bar_history"]
        del payload["server_time"]
        self.assertEqual({}, validated_bar_history(payload))
        registry = BridgeRegistry()
        registry.record_snapshot(payload)
        self.assertTrue(registry.overview_payload()["available"])
        strategy = StrategyEngine()
        self.assertEqual(1, strategy.ingest_snapshot(payload)["bars_seen"]["M1"])

    def test_last_tick_time_is_preserved_separately_from_snapshot_freshness(self):
        payload = history_snapshot()
        friday_tick_msc = (payload["server_time"] - 2 * 86400) * 1000
        payload["tick_time_msc"] = friday_tick_msc
        registry = BridgeRegistry()
        registry.record_snapshot(payload)
        overview = registry.overview_payload()
        self.assertTrue(overview["available"])
        self.assertEqual(friday_tick_msc, overview["tick_time_msc"])
        self.assertEqual(payload["server_time"], overview["server_time"])
        self.assertIsNotNone(overview["snapshot_received_utc"])
        for invalid in (-1, True, "old"):
            payload["tick_time_msc"] = invalid
            with self.assertRaises(BridgeSnapshotError):
                registry.record_snapshot(payload)

    def test_ea_reader_waits_for_complete_bounded_frame_before_utf8_decode(self):
        source = (pathlib.Path(__file__).resolve().parents[2] / "mql5" / "XAUPY_Bridge_EA.mq5").read_text(encoding="utf-8")
        reader = source.split("bool ReadResponseLine(", 1)[1].split("bool SendRequest(", 1)[0]
        self.assertIn("SocketIsReadable(g_socket)", reader)
        self.assertIn("SocketRead(g_socket, chunk, read_size, remaining_ms)", reader)
        self.assertIn("MathMin(available, 16384)", reader)
        self.assertIn("GetTickCount64() - started_ms < InpSocketTimeoutMs", reader)
        self.assertIn("max_response_bytes = 1024 * 1024", reader)
        self.assertIn("ArrayCopy(response_bytes, chunk, total, 0, append_count)", reader)
        decode = reader.index("CharArrayToString(response_bytes")
        self.assertLess(reader.index("if(newline_at >= 0)"), decode)
        self.assertNotIn("CharArrayToString(chunk", reader)
        self.assertNotIn("SocketRead(g_socket, recv, 65535", source)


class HistoryProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_closed_history_packet_reaches_desktop_projection(self):
        with tempfile.TemporaryDirectory() as state_dir, tempfile.TemporaryDirectory() as log_dir:
            server = EngineServer(port=0, state_dir=state_dir, journal_dir=log_dir)
            await server.start()
            reader, writer = await asyncio.open_connection("127.0.0.1", server.bound_port, limit=MAX_LINE_BYTES)
            try:
                request = Envelope.create("bridge_snapshot", history_snapshot())
                encoded = (request.to_json() + "\n").encode()
                self.assertGreater(len(encoded), 65536)
                self.assertLess(len(encoded), MAX_LINE_BYTES)
                writer.write(encoded)
                await writer.drain()
                ack = Envelope.from_json((await asyncio.wait_for(reader.readline(), 3)).decode().strip())
                self.assertEqual("bridge_snapshot_ack", ack.type)
                heartbeat = Envelope.create("heartbeat")
                writer.write((heartbeat.to_json() + "\n").encode())
                await writer.drain()
                result = json.loads((await asyncio.wait_for(reader.readline(), 3)).decode())
                overview = result["payload"]["overview"]
                self.assertEqual(256, len(overview["bar_history"]["M30"]))
                self.assertEqual(256, len(overview["bar_history"]["D1"]))
                self.assertEqual(256, result["payload"]["strategy"]["bars_seen"]["M30"])
                self.assertFalse(result["payload"]["execution_enabled"])
                self.assertEqual(0, result["payload"]["strategy"]["signal_sequence"])
            finally:
                writer.close()
                await writer.wait_closed()
                await server.close()


if __name__ == "__main__":
    unittest.main()
