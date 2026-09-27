from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xaupy_engine.tick_protocol import validate_tick_payload
from xaupy_engine.contracts import Envelope
from xaupy_engine.server import EngineServer


def packet():
    return {"symbol": "XAUUSD", "server_time": 1800000000, "tick_batch": {
        "stream_id": "test-stream", "sequence": 1, "complete": False,
        "ticks": [dict(time_msc=1799999999123, bid=2000, ask=2001, last=0, flags=6)]}}


class TickProtocolTests(unittest.TestCase):
    def test_equal_millisecond_ticks_keep_order_and_zero_quotes_are_transportable(self):
        data = packet()
        data["tick_batch"]["ticks"] += [dict(time_msc=1799999999123, bid=0, ask=0, last=0, flags=6)]
        validate_tick_payload(data)
        self.assertEqual([2000, 0], [t["bid"] for t in data["tick_batch"]["ticks"]])

    def test_oversize_out_of_order_nonfinite_and_future_rejected(self):
        mutations = [lambda p: p["tick_batch"].update(ticks=p["tick_batch"]["ticks"]*1001),
            lambda p: p["tick_batch"]["ticks"].append(dict(time_msc=1, bid=1, ask=1, last=0, flags=6)),
            lambda p: p["tick_batch"]["ticks"][0].update(bid=float("inf")),
            lambda p: p["tick_batch"]["ticks"][0].update(time_msc=1800000010000),
            lambda p: p["tick_batch"].update(sequence=True)]
        for mutate in mutations:
            data = packet(); mutate(data)
            with self.subTest(data=str(data)[:100]), self.assertRaises(ValueError): validate_tick_payload(data)

    def test_server_only_ingests_fresh_matching_symbol(self):
        with tempfile.TemporaryDirectory() as root:
            server = EngineServer(port=0, state_dir=Path(root)/"state", journal_dir=Path(root)/"logs")
            request = Envelope.create("bridge_ticks", packet())
            with patch.object(server.strategy, "ingest_tick_batch", return_value={"state":"WAIT_INTRABAR"}) as ingest:
                response, _ = server._dispatch(request)
                self.assertFalse(response.payload["accepted"])
                ingest.assert_not_called()
                self.assertEqual("MARKET_DATA_STALE", server.strategy.last_reset_reason)
                with patch.object(server.bridge, "market_data_connected", return_value=True), patch.object(server.bridge, "status") as status:
                    status.return_value.symbol = "XAUUSD"
                    response, _ = server._dispatch(request)
                    self.assertTrue(response.payload["accepted"])
                    self.assertFalse(response.payload["execution_enabled"])
                    ingest.assert_called_once()
                    status.return_value.symbol = "EURUSD"
                    response, _ = server._dispatch(request)
                    self.assertFalse(response.payload["accepted"])
                    self.assertEqual(1, ingest.call_count)

    def test_transport_reports_real_receipt_even_when_closed_bar_mode_is_default(self):
        with tempfile.TemporaryDirectory() as root:
            server = EngineServer(port=0, state_dir=Path(root)/"state", journal_dir=Path(root)/"logs")
            self.assertTrue(server.active_profile["trigger"]["confirm_closed_bar"])
            request = Envelope.create("bridge_ticks", packet())
            server._dispatch(request)
            self.assertEqual(0, server.tick_transport.payload()["received_ticks"])
            with patch.object(server.bridge, "market_data_connected", return_value=True), patch.object(server.bridge, "status") as status:
                status.return_value.symbol = "XAUUSD"
                result, _ = server._dispatch(request)
                self.assertEqual(1, result.payload["tick_transport"]["received_ticks"])
                self.assertEqual(1, result.payload["tick_transport"]["accepted_batches"])
                self.assertIsNotNone(result.payload["tick_transport"]["last_received_utc"])
                self.assertFalse(result.payload["tick_transport"]["last_complete"])
                self.assertEqual(0, result.payload["strategy"]["signal_sequence"])
            heartbeat, _ = server._dispatch(Envelope.create("heartbeat"))
            self.assertEqual("test-stream", heartbeat.payload["tick_transport"]["last_stream_id"])
            self.assertIsNotNone(heartbeat.payload["tick_transport"]["age_ms"])
            self.assertFalse(heartbeat.payload["execution_enabled"])


if __name__ == "__main__": unittest.main()
