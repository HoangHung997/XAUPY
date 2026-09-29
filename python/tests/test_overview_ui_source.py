from ui_source_support import read_xaml
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
XAML = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml"
CODE = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml.cs"
REFERENCE = ROOT / "docs" / "ui-reference" / "Tab Tổng Quan.png"


class OverviewUiSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xaml = read_xaml(XAML)
        cls.code = CODE.read_text(encoding="utf-8")

    def test_visual_reference_exists(self):
        self.assertTrue(REFERENCE.exists())
        self.assertGreater(REFERENCE.stat().st_size, 100_000)

    def test_overview_contains_all_reference_information_groups(self):
        required_text = (
            "N30 Control Center",
            "XAUUSD",
            "Trạng thái EA",
            "Tài khoản giao dịch",
            "Kết nối &amp; Hệ thống",
            "Python Engine",
            "EA Bridge",
            "Thông tin chiến lược (Realtime)",
            "Công cụ &amp; Tham số đầy đủ (Trung tâm cấu hình)",
            "Lệnh gần đây",
            "Nhật ký hệ thống",
        )
        for value in required_text:
            with self.subTest(value=value):
                self.assertIn(value, self.xaml)

    def test_overview_controls_are_data_driven_and_named(self):
        required_names = (
            "BidValue",
            "AskValue",
            "SpreadValue",
            "BalanceValue",
            "EquityValue",
            "MarginFreeValue",
            "EngineStateText",
            "BridgeStateText",
            "DirectionTfValue",
            "PullbackTfValue",
            "TriggerTfValue",
            "PositionsCountValue",
            "OrdersCountValue",
            "QuickLogText",
        )
        for name in required_names:
            with self.subTest(name=name):
                self.assertIn(f'x:Name="{name}"', self.xaml)
                self.assertIn(f'"{name}"', self.code)

    def test_overview_uses_approved_horizontal_shell_not_old_sidebar_navigation(self):
        self.assertIn('ColumnDefinitions="*,*,*,*,*,*,*,*,*,*,175"', self.xaml)
        self.assertIn('Classes="navTab active"', self.xaml)
        self.assertIn('x:Name="LiveSidebar"', self.xaml)
        self.assertNotIn('ColumnDefinitions="220,*"', self.xaml)

    def test_tools_and_settings_have_real_dashboards(self):
        self.assertIn('x:Name="ToolsView"', self.xaml)
        self.assertIn('x:Name="SettingsView"', self.xaml)
        self.assertIn('_toolsDashboard.EnsureLoadedAsync', self.code)
        self.assertIn('_settingsDashboard.EnsureLoadedAsync', self.code)

    def test_user_execution_state_remains_visible(self):
        # The shell must display the actual execution state selected by the user.
        self.assertIn('x:Name="GuardianReasonValue"', self.xaml)
        self.assertNotIn('Text="LOCKED"', self.xaml)
        self.assertIn('ExecutionPresentation.Mode(e.Execution)', self.code)
        self.assertIn('ExecutionPresentation.Summary(e.Execution)', self.code)
        self.assertNotIn("broker execution hiện đang khóa", self.code)


if __name__ == "__main__":
    unittest.main()
