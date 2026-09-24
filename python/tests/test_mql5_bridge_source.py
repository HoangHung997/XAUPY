import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "mql5" / "XAUPY_Bridge_EA.mq5"


class Mql5BridgeSourceSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_task003_execution_is_hard_locked(self):
        self.assertIn("TASK003_EXECUTION_LOCKED = true", self.text)
        self.assertIn('"execution_locked":true', self.text)
        self.assertIn('"execution_ready":false', self.text)

    def test_no_order_execution_api_exists(self):
        forbidden = (
            "OrderSend(",
            "OrderSendAsync(",
            "CTrade ",
            "CTrade\t",
            "#include <Trade/Trade.mqh>",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, self.text)

    def test_loopback_guard_exists(self):
        self.assertIn('InpHost != "127.0.0.1"', self.text)
        self.assertIn('InpHost != "localhost"', self.text)

    def test_required_timeframes_are_exported(self):
        for timeframe in ("PERIOD_M1","PERIOD_M3","PERIOD_M5","PERIOD_M15","PERIOD_M30","PERIOD_H1","PERIOD_H2","PERIOD_H4"):
            with self.subTest(timeframe=timeframe):
                self.assertIn(timeframe, self.text)

    def test_socket_data_channel_exists(self):
        for token in ("SocketCreate(", "SocketConnect(", "SocketSend(", "SocketRead(", "bridge_snapshot"):
            with self.subTest(token=token):
                self.assertIn(token, self.text)


if __name__ == "__main__":
    unittest.main()
