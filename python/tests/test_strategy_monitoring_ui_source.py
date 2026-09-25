import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAIN_XAML = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml"
MAIN_CODE = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml.cs"
STRATEGY_XAML = ROOT / "src" / "XAUPY.Desktop" / "StrategyDashboard.axaml"
STRATEGY_CODE = ROOT / "src" / "XAUPY.Desktop" / "StrategyDashboard.axaml.cs"
MONITOR_XAML = ROOT / "src" / "XAUPY.Desktop" / "MonitoringDashboard.axaml"
MONITOR_CODE = ROOT / "src" / "XAUPY.Desktop" / "MonitoringDashboard.axaml.cs"
SUPERVISOR = ROOT / "src" / "XAUPY.Ipc" / "EngineProcessSupervisor.cs"
MODEL = ROOT / "src" / "XAUPY.Ipc" / "StrategyModels.cs"
STRATEGY_REFERENCE = ROOT / "docs" / "ui-reference" / "Tab Chiến Lược.png"
MONITOR_REFERENCE = ROOT / "docs" / "ui-reference" / "Tab Giám Sát.png"


class StrategyMonitoringUiSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_xaml = MAIN_XAML.read_text(encoding="utf-8")
        cls.main_code = MAIN_CODE.read_text(encoding="utf-8")
        cls.strategy_xaml = STRATEGY_XAML.read_text(encoding="utf-8")
        cls.strategy_code = STRATEGY_CODE.read_text(encoding="utf-8")
        cls.monitor_xaml = MONITOR_XAML.read_text(encoding="utf-8")
        cls.monitor_code = MONITOR_CODE.read_text(encoding="utf-8")
        cls.supervisor = SUPERVISOR.read_text(encoding="utf-8")
        cls.model = MODEL.read_text(encoding="utf-8")

    def test_approved_strategy_and_monitoring_references_exist(self):
        for path in (STRATEGY_REFERENCE, MONITOR_REFERENCE):
            with self.subTest(path=path.name):
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 100_000)

    def test_both_tabs_are_real_hosted_controls_not_placeholders(self):
        self.assertIn('x:Name="StrategyDashboard"', self.main_xaml)
        self.assertIn('x:Name="MonitoringDashboard"', self.main_xaml)
        self.assertIn('Tag="strategy"', self.main_xaml)
        self.assertIn('Tag="monitoring"', self.main_xaml)
        self.assertIn("_strategyDashboard.IsVisible = strategy", self.main_code)
        self.assertIn("_monitoringDashboard.IsVisible = monitoring", self.main_code)

    def test_strategy_tab_contains_reference_information_hierarchy(self):
        for value in (
            "Direction → Pullback → Trigger",
            "Bộ lọc &amp; chỉ báo realtime",
            "Chiến lược hiện tại",
            "Trạng thái điều kiện (Realtime)",
            "Warm-up / dữ liệu",
            "Tín hiệu gần nhất",
            "EXECUTION LOCKED",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.strategy_xaml)

    def test_strategy_tab_is_projection_driven(self):
        for name in (
            "StrategyStateText",
            "DirectionMaText",
            "PullbackRsiText",
            "TriggerRsiText",
            "AdxText",
            "AtrText",
            "BarsSeenText",
            "WarmupText",
            "LastSignalText",
        ):
            with self.subTest(name=name):
                self.assertIn(f'x:Name="{name}"', self.strategy_xaml)
                self.assertIn(f'"{name}"', self.strategy_code)

        self.assertIn("StrategySnapshot", self.strategy_code)
        self.assertIn("e.Strategy", self.main_code)

    def test_monitoring_tab_uses_only_real_session_snapshots(self):
        self.assertIn("Live quote monitor", self.monitor_xaml)
        self.assertIn("không backfill số giả", self.monitor_xaml)
        self.assertIn("overview.SnapshotReceivedUtc", self.monitor_code)
        self.assertIn("overview.Bars.TryGetValue", self.monitor_code)
        self.assertIn("REAL HEARTBEAT QUOTES", self.monitor_xaml)
        self.assertNotIn("mock", self.monitor_code.lower())

    def test_unimplemented_monitoring_backends_are_explicit_not_faked(self):
        self.assertIn("Chưa có realtime session/news backend", self.monitor_xaml)
        self.assertIn("CPU/RAM diagnostics thuộc Task 014", self.monitor_xaml)
        self.assertIn("Không có manual/auto broker action", self.monitor_xaml)

    def test_strategy_projection_is_parsed_and_guarded_by_supervisor(self):
        self.assertIn("StrategySnapshot.FromHeartbeatPayload", self.supervisor)
        self.assertIn("RejectUnexpectedStrategyExecutionEnable", self.supervisor)
        self.assertIn("TradingEnabled", self.model)
        self.assertIn("ExecutionEnabled", self.model)
        self.assertIn("desktop_version = \"0.8.0-task008\"", self.supervisor)

    def test_main_overview_now_uses_real_strategy_state(self):
        self.assertIn('x:Name="StrategyStateValue"', self.main_xaml)
        self.assertIn("ApplyStrategySnapshot", self.main_code)
        self.assertIn("strategy.State", self.main_code)
        self.assertIn("execution vẫn khóa", self.main_xaml)

    def test_future_tabs_keep_explicit_placeholder(self):
        self.assertIn('x:Name="PlaceholderContent"', self.main_xaml)
        self.assertIn("Task 008 đã triển khai Tổng quan + Cấu hình + Chiến lược + Giám sát", self.main_code)
        self.assertIn("Không hiển thị dữ liệu giả", self.main_xaml)


if __name__ == "__main__":
    unittest.main()
