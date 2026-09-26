import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAIN_XAML = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml"
MAIN_CODE = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml.cs"
ORDERS_XAML = ROOT / "src" / "XAUPY.Desktop" / "OrdersPositionsDashboard.axaml"
ORDERS_CODE = ROOT / "src" / "XAUPY.Desktop" / "OrdersPositionsDashboard.axaml.cs"
SUPERVISOR = ROOT / "src" / "XAUPY.Ipc" / "EngineProcessSupervisor.cs"
MODEL = ROOT / "src" / "XAUPY.Ipc" / "OrdersPositionsModels.cs"
REFERENCE = ROOT / "docs" / "ui-reference" / "Tab Lệnh & Vị thế.png"


class Task009OrdersUiSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_xaml = MAIN_XAML.read_text(encoding="utf-8")
        cls.main_code = MAIN_CODE.read_text(encoding="utf-8")
        cls.xaml = ORDERS_XAML.read_text(encoding="utf-8")
        cls.code = ORDERS_CODE.read_text(encoding="utf-8")
        cls.supervisor = SUPERVISOR.read_text(encoding="utf-8")
        cls.model = MODEL.read_text(encoding="utf-8")

    def test_approved_reference_exists(self):
        self.assertTrue(REFERENCE.exists())
        self.assertGreater(REFERENCE.stat().st_size, 100_000)

    def test_orders_tab_is_real_full_width_host_not_placeholder(self):
        self.assertIn('x:Name="OrdersPositionsDashboard"', self.main_xaml)
        self.assertIn('Grid.ColumnSpan="2"', self.main_xaml)
        self.assertIn('_ordersPositionsDashboard.IsVisible = orders', self.main_code)
        self.assertIn('_ordersPositionsDashboard.Apply(e.OrdersPositions', self.main_code)

    def test_reference_kpi_and_table_zones_exist(self):
        for value in (
            "Tổng P/L đang mở",
            "P/L đã thực hiện",
            "Tổng mức tiếp xúc",
            "Rủi ro hiện tại",
            "Lệnh chờ đang hoạt động",
            "Vị thế đang mở",
            "Lịch sử giao dịch (Deals)",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.xaml)

    def test_reference_manual_controls_exist_in_order(self):
        for value in (
            "Đóng tất cả vị thế",
            "Đóng lãi",
            "Đóng lỗ",
            "Đóng một phần",
            "Chuyển SL về BE",
            "Trailing Stop",
            "Hủy tất cả lệnh chờ",
            "Thị trường",
            "Lệnh chờ",
            "Thông tin",
            "BUY",
            "SELL",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.xaml)

    def test_tables_render_ticket_level_real_data(self):
        for name in ("PositionsRowsHost", "PendingRowsHost", "DealsRowsHost"):
            self.assertIn(f'x:Name="{name}"', self.xaml)
            self.assertIn(f'"{name}"', self.code)
        self.assertIn("PositionSnapshot", self.code)
        self.assertIn("PendingOrderSnapshot", self.code)
        self.assertIn("DealSnapshot", self.code)
        self.assertNotIn("32874561", self.xaml)
        self.assertNotIn("4282.30", self.xaml)

    def test_quote_chart_only_advances_on_real_snapshot_token(self):
        self.assertIn("book.SnapshotReceivedUtc", self.code)
        self.assertIn("book.Bid.HasValue", self.code)
        self.assertIn("_quotes.Clear()", self.code)
        self.assertIn("REAL SESSION QUOTES", self.xaml)

    def test_manual_controls_are_simulation_only_and_confirmed(self):
        self.assertIn("SIMULATION ONLY", self.xaml)
        self.assertIn("BROKER EXECUTION LOCKED", self.xaml)
        self.assertIn('x:Name="ConfirmCloseCheck"', self.xaml)
        self.assertIn('x:Name="ManualConfirmCheck"', self.xaml)
        self.assertIn("SimulateManualActionAsync", self.code)
        self.assertNotIn("OrderSend", self.code)
        self.assertNotIn("CTrade", self.code)

    def test_supervisor_rejects_execution_unlock(self):
        self.assertIn("OrdersPositionsSnapshot.FromHeartbeatPayload", self.supervisor)
        self.assertIn("RejectUnexpectedOrdersExecutionEnable", self.supervisor)
        self.assertIn("BrokerExecutionLocked", self.model)
        self.assertIn("SimulationOnly", self.model)
        self.assertIn('desktop_version = "0.13.0-task013"', self.supervisor)

    def test_no_old_task009_placeholder_wording_remains(self):
        self.assertNotIn("Execution và màn hình quản lý lệnh thuộc Task 009", self.main_code)


if __name__ == "__main__":
    unittest.main()
