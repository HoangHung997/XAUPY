import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
XAML = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml"
CODE = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml.cs"
REFERENCE = ROOT / "docs" / "ui-reference" / "Tab Tổng Quan.png"


class OverviewUiSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xaml = XAML.read_text(encoding="utf-8")
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

    def test_unimplemented_tabs_have_explicit_placeholder_instead_of_fake_data(self):
        self.assertIn('x:Name="PlaceholderContent"', self.xaml)
        self.assertIn("không hiển thị dữ liệu giao dịch giả", self.xaml)
        self.assertIn("đã triển khai Tổng quan + Cấu hình", self.code)

    def test_execution_lock_remains_visible(self):
        # The approved screenshot does not require a giant global lock badge,
        # but the hard safety state must remain visible in the rendered shell.
        self.assertIn('x:Name="GuardianReasonValue"', self.xaml)
        self.assertIn('Text="LOCKED"', self.xaml)
        self.assertIn("broker execution hiện đang khóa", self.code)


if __name__ == "__main__":
    unittest.main()
