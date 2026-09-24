import pathlib
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.bridge_state import BridgeRegistry, BridgeSnapshotError


def snapshot():
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


class BridgeRegistryTests(unittest.TestCase):
    def test_valid_snapshot_is_connected_but_execution_locked(self):
        registry = BridgeRegistry(stale_seconds=1.0)
        registry.record_hello({"bridge_version": "0.3.0-task003", "symbol": "XAUUSD"})
        registry.record_snapshot(snapshot())

        status = registry.status()
        self.assertTrue(status.connected)
        self.assertEqual("XAUUSD", status.symbol)
        self.assertEqual("DEMO", status.account_trade_mode)
        self.assertFalse(status.execution_ready)
        self.assertTrue(status.execution_locked)
        self.assertEqual("TASK003_EXECUTION_LOCKED", status.guardian_reason)
        self.assertEqual(1, status.snapshots_total)

    def test_unlocked_guardian_is_rejected(self):
        payload = snapshot()
        payload["guardian"]["execution_locked"] = False

        registry = BridgeRegistry()
        with self.assertRaises(BridgeSnapshotError):
            registry.record_snapshot(payload)

    def test_execution_ready_is_rejected(self):
        payload = snapshot()
        payload["guardian"]["execution_ready"] = True

        registry = BridgeRegistry()
        with self.assertRaises(BridgeSnapshotError):
            registry.record_snapshot(payload)

    def test_all_eight_timeframes_are_required(self):
        payload = snapshot()
        del payload["bars"]["M3"]

        registry = BridgeRegistry()
        with self.assertRaises(BridgeSnapshotError):
            registry.record_snapshot(payload)

    def test_bridge_becomes_stale(self):
        registry = BridgeRegistry(stale_seconds=0.02)
        registry.record_snapshot(snapshot())
        self.assertTrue(registry.status().connected)
        time.sleep(0.04)
        self.assertFalse(registry.status().connected)


if __name__ == "__main__":
    unittest.main()
