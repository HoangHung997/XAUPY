import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.contracts import Envelope, PROTOCOL_VERSION, ProtocolError


class EnvelopeContractTests(unittest.TestCase):
    def test_round_trip_preserves_request_id(self) -> None:
        original = Envelope.create("heartbeat", {"component": "desktop"})
        restored = Envelope.from_json(original.to_json())
        self.assertEqual(original.request_id, restored.request_id)
        self.assertEqual("heartbeat", restored.type)
        self.assertEqual(PROTOCOL_VERSION, restored.schema_version)

    def test_response_correlates_to_request(self) -> None:
        request = Envelope.create("hello", {"component": "desktop"})
        response = Envelope.response("hello_ack", request.request_id, {"trading_enabled": False})
        self.assertEqual(request.request_id, response.request_id)
        self.assertFalse(response.payload["trading_enabled"])

    def test_unique_request_ids(self) -> None:
        first = Envelope.create("heartbeat")
        second = Envelope.create("heartbeat")
        self.assertNotEqual(first.request_id, second.request_id)

    def test_unknown_schema_is_rejected(self) -> None:
        raw = json.loads(Envelope.create("heartbeat").to_json())
        raw["schema_version"] = 999
        with self.assertRaises(ProtocolError):
            Envelope.from_json(json.dumps(raw))

    def test_payload_must_be_object(self) -> None:
        raw = json.loads(Envelope.create("heartbeat").to_json())
        raw["payload"] = []
        with self.assertRaises(ProtocolError):
            Envelope.from_json(json.dumps(raw))


if __name__ == "__main__":
    unittest.main()
