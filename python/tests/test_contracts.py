import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.contracts import Heartbeat, foundation_heartbeat


class HeartbeatContractTests(unittest.TestCase):
    def test_foundation_never_enables_trading(self) -> None:
        heartbeat = foundation_heartbeat()
        self.assertFalse(heartbeat.trading_enabled)
        self.assertEqual("python-engine", heartbeat.component)
        self.assertEqual(1, heartbeat.schema_version)

    def test_json_round_trip_is_lossless(self) -> None:
        original = foundation_heartbeat()
        restored = Heartbeat.from_json(original.to_json())
        self.assertEqual(original, restored)

    def test_payload_is_valid_json(self) -> None:
        payload = json.loads(foundation_heartbeat().to_json())
        self.assertEqual("ready", payload["state"])
        self.assertIs(payload["trading_enabled"], False)


if __name__ == "__main__":
    unittest.main()
