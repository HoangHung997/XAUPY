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
            "XAUUSD • Live Quote",
            "Python Engine",
            "MT5 Bridge",
            "BALANCE",
            "EQUITY",
            "FREE MARGIN",
            "Chiến lược realtime",
            "Lệnh gần đây",
            "Log nhanh",
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

    def test_unimplemented_tabs_have_explicit_placeholder_instead_of_fake_data(self):
        self.assertIn('x:Name="PlaceholderContent"', self.xaml)
        self.assertIn("Không hiển thị dữ liệu giả", self.xaml)
        self.assertIn("Task 005 chỉ triển khai", self.code)

    def test_execution_lock_remains_visible(self):
        self.assertIn("EXECUTION LOCKED", self.xaml)


if __name__ == "__main__":
    unittest.main()
