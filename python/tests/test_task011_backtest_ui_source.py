import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAIN_XAML = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml"
MAIN_CODE = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml.cs"
BACKTEST_XAML = ROOT / "src" / "XAUPY.Desktop" / "BacktestDashboard.axaml"
BACKTEST_CODE = ROOT / "src" / "XAUPY.Desktop" / "BacktestDashboard.axaml.cs"
CHART_CODE = ROOT / "src" / "XAUPY.Desktop" / "BacktestChartControl.cs"
SUPERVISOR = ROOT / "src" / "XAUPY.Ipc" / "EngineProcessSupervisor.cs"
MODEL = ROOT / "src" / "XAUPY.Ipc" / "BacktestModels.cs"
SPEC = ROOT / "docs" / "TASK011_BACKTEST_PARITY_SPEC.md"
REFERENCE = ROOT / "docs" / "ui-reference" / "Tab BackTest.png"


class Task011BacktestUiSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_xaml = MAIN_XAML.read_text(encoding="utf-8")
        cls.main_code = MAIN_CODE.read_text(encoding="utf-8")
        cls.xaml = BACKTEST_XAML.read_text(encoding="utf-8")
        cls.code = BACKTEST_CODE.read_text(encoding="utf-8")
        cls.chart = CHART_CODE.read_text(encoding="utf-8")
        cls.supervisor = SUPERVISOR.read_text(encoding="utf-8")
        cls.model = MODEL.read_text(encoding="utf-8")
        cls.spec = SPEC.read_text(encoding="utf-8")

    def test_approved_reference_exists(self):
        self.assertTrue(REFERENCE.exists())
        self.assertGreater(REFERENCE.stat().st_size, 100_000)

    def test_backtest_is_real_host_with_live_sidebar(self):
        self.assertIn('x:Name="BacktestDashboard"', self.main_xaml)
        self.assertIn('Grid.Column="1"', self.main_xaml)
        self.assertIn('_backtestDashboard.IsVisible = backtest', self.main_code)
        self.assertIn('liveSidebar = overview || strategy || monitoring || backtest || optimization', self.main_code)
        self.assertIn('_backtestDashboard.EnsureLoadedAsync(force: true)', self.main_code)

    def test_reference_configuration_zone_exists(self):
        for value in (
            "Cấu hình Backtest",
            "Symbol",
            "Khung dữ liệu",
            "Từ ngày",
            "Đến ngày",
            "Model",
            "Spread (pip)",
            "Hoa hồng (USD/lot)",
            "Chạy Backtest",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.xaml)

    def test_reference_result_kpis_exist(self):
        for value in (
            "Lợi nhuận ròng",
            "Tỷ lệ thắng",
            "Profit Factor",
            "Drawdown tối đa",
            "Tổng số lệnh",
            "Lợi nhuận trung bình",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.xaml)

    def test_reference_chart_and_table_zones_exist(self):
        for value in (
            "Đường cong vốn (Equity Curve)",
            "Drawdown (Mức sụt giảm vốn)",
            "Danh sách kết quả Backtest",
            "Danh sách giao dịch (Backtest)",
            "So sánh kết quả",
            "Xuất báo cáo",
            "Lưu kết quả",
            "Tải từ file",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.xaml)

    def test_runtime_results_are_not_mock_numbers(self):
        self.assertIn('x:Name="BacktestHistoryRowsHost"', self.xaml)
        self.assertIn('x:Name="BacktestTradeRowsHost"', self.xaml)
        self.assertIn('Text="—"', self.xaml)
        for mock_value in ("12,458.72", "68.42%", "2.15", "8.73%"):
            with self.subTest(mock_value=mock_value):
                self.assertNotIn(mock_value, self.xaml)

    def test_ui_calls_real_backtest_ipc(self):
        for method in (
            "InspectBacktestDatasetAsync",
            "RunBacktestAsync",
            "QueryBacktestHistoryAsync",
            "GetBacktestResultAsync",
            "DeleteBacktestResultAsync",
        ):
            with self.subTest(method=method):
                self.assertIn(method, self.code)
                self.assertIn(method, self.supervisor)

        for message in (
            "backtest_dataset_inspect",
            "backtest_run",
            "backtest_history_query",
            "backtest_result_get",
            "backtest_result_delete",
        ):
            with self.subTest(message=message):
                self.assertIn(message, self.supervisor)

    def test_charts_are_data_driven(self):
        self.assertIn('x:Name="EquityChart"', self.xaml)
        self.assertIn('x:Name="DrawdownChart"', self.xaml)
        self.assertIn("SetEquityData", self.code)
        self.assertIn("SetDrawdownData", self.code)
        self.assertIn("BacktestEquityPoint", self.chart)
        self.assertIn("BacktestDrawdownPoint", self.chart)

    def test_models_include_reproducibility_and_trade_evidence(self):
        for value in (
            "DatasetFingerprint",
            "ResultHash",
            "ProfileHash",
            "MaePriceUnits",
            "MfePriceUnits",
            "TradeTotal",
            "SkippedSignals",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.model)

    def test_every_tick_mock_is_not_claimed_as_runtime_model(self):
        self.assertIn("M1 OHLC deterministic parity", self.xaml)
        self.assertIn("Every tick", self.spec)
        self.assertIn("does not yet have an", self.spec)
        self.assertNotIn("Every tick (chính xác nhất)", self.xaml)

    def test_task011_version_and_safety_guards_remain(self):
        self.assertIn('desktop_version = "0.13.0-task013"', self.supervisor)
        self.assertIn("RejectUnexpectedExecutionEnable", self.supervisor)
        self.assertIn("RejectUnexpectedOrdersExecutionEnable", self.supervisor)
        self.assertIn("Task 013 manual action response violated simulation-only safety", self.supervisor)


if __name__ == "__main__":
    unittest.main()
