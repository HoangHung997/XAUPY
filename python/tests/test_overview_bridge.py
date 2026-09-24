import pathlib
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.bridge_state import BridgeRegistry


TIMEFRAMES = ("M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4")


def snapshot():
    bars = {}
    for index, tf in enumerate(TIMEFRAMES):
        bars[tf] = {
            "time": 1790240000 + index * 60,
            "open": 4280.0 + index,
            "high": 4282.0 + index,
            "low": 4279.0 + index,
            "close": 4281.0 + index,
            "tick_volume": 100 + index,
        }

    return {
        "bridge_version": "0.3.0-task003",
        "symbol": "XAUUSD",
        "terminal_connected": True,
        "account_trade_mode": "DEMO",
        "account_login": 123456,
        "account_currency": "USD",
        "balance": 10000.0,
        "equity": 10025.5,
        "margin_free": 9900.25,
        "bid": 4281.10,
        "ask": 4281.35,
        "spread_points": 25.0,
        "positions_count": 1,
        "orders_count": 2,
        "guardian": {
            "execution_locked": True,
            "execution_ready": False,
            "reason": "TASK003_EXECUTION_LOCKED",
        },
        "bars": bars,
    }


class OverviewProjectionTests(unittest.TestCase):
    def test_live_overview_projects_real_bridge_fields(self):
        registry = BridgeRegistry(stale_seconds=1.0)
        registry.record_snapshot(snapshot())

        overview = registry.overview_payload()

        self.assertTrue(overview["available"])
        self.assertEqual("XAUUSD", overview["symbol"])
        self.assertEqual("DEMO", overview["account_trade_mode"])
        self.assertEqual("USD", overview["account_currency"])
        self.assertEqual(4281.10, overview["bid"])
        self.assertEqual(4281.35, overview["ask"])
        self.assertEqual(10000.0, overview["balance"])
        self.assertEqual(10025.5, overview["equity"])
        self.assertEqual(9900.25, overview["margin_free"])
        self.assertEqual(1, overview["positions_count"])
        self.assertEqual(2, overview["orders_count"])
        self.assertEqual(set(TIMEFRAMES), set(overview["bars"]))
        self.assertIsNotNone(overview["snapshot_received_utc"])

    def test_stale_bridge_never_advertises_market_values_as_live(self):
        registry = BridgeRegistry(stale_seconds=0.02)
        registry.record_snapshot(snapshot())
        time.sleep(0.04)

        overview = registry.overview_payload()

        self.assertFalse(overview["available"])
        self.assertIsNone(overview["bid"])
        self.assertIsNone(overview["ask"])
        self.assertIsNone(overview["balance"])
        self.assertEqual({}, overview["bars"])

    def test_empty_registry_has_explicit_unavailable_overview(self):
        overview = BridgeRegistry().overview_payload()
        self.assertFalse(overview["available"])
        self.assertIsNone(overview["snapshot_received_utc"])
        self.assertEqual(0, overview["positions_count"])
        self.assertEqual(0, overview["orders_count"])


if __name__ == "__main__":
    unittest.main()
