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
        self.assertIn("execution_locked", self.text)
        self.assertIn("execution_ready", self.text)
        self.assertIn("TASK003_EXECUTION_LOCKED", self.text)

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

    def test_task009_exports_owned_ticket_level_order_book(self):
        for token in (
            "JsonPositions()",
            "JsonOrders()",
            "JsonDeals()",
            'JsonKey("positions")',
            'JsonKey("orders")',
            'JsonKey("deals")',
            "DEAL_POSITION_ID",
            "HistoryPositionEntryPrice",
            "OwnDailyRealized",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.text)

    def test_task009_still_has_no_broker_mutation_path(self):
        self.assertIn("ORDER BOOK ACTIVE; BROKER EXECUTION LOCKED", self.text)
        self.assertNotIn("PositionClose(", self.text)
        self.assertNotIn("PositionModify(", self.text)
        self.assertNotIn("OrderDelete(", self.text)

    def test_socket_data_channel_exists(self):
        for token in ("SocketCreate(", "SocketConnect(", "SocketSend(", "SocketRead(", "bridge_snapshot"):
            with self.subTest(token=token):
                self.assertIn(token, self.text)


if __name__ == "__main__":
    unittest.main()
