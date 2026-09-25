import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
EDITOR_XAML = ROOT / "src" / "XAUPY.Desktop" / "ConfigurationEditor.axaml"
EDITOR_CODE = ROOT / "src" / "XAUPY.Desktop" / "ConfigurationEditor.axaml.cs"
MAIN_XAML = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml"
MAIN_CODE = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml.cs"
REFERENCE = ROOT / "docs" / "ui-reference" / "Tab Cấu Hình.png"


class ConfigurationUiSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xaml = EDITOR_XAML.read_text(encoding="utf-8")
        cls.code = EDITOR_CODE.read_text(encoding="utf-8")
        cls.main_xaml = MAIN_XAML.read_text(encoding="utf-8")
        cls.main_code = MAIN_CODE.read_text(encoding="utf-8")

    def test_visual_reference_exists(self):
        self.assertTrue(REFERENCE.exists())
        self.assertGreater(REFERENCE.stat().st_size, 100_000)

    def test_configuration_editor_is_hosted_as_real_tab(self):
        self.assertIn('x:Name="ConfigurationEditor"', self.main_xaml)
        self.assertIn("ConfigurationEditor", self.main_code)
        self.assertIn('Tag="configuration"', self.main_xaml)

    def test_toolbar_has_required_profile_and_set_actions(self):
        for label in (
            "Mặc định",
            "Hoàn tác Active",
            "Xác thực",
            "Áp dụng Active",
            "Mở JSON",
            "Lưu JSON",
            "Nhập .set",
            "Xuất .set",
        ):
            with self.subTest(label=label):
                self.assertIn(label, self.xaml)

    def test_editor_is_schema_driven_and_searchable(self):
        self.assertIn('x:Name="SearchBox"', self.xaml)
        self.assertIn("GetConfigSchemaAsync", self.code)
        self.assertIn("BuildSchema", self.code)
        self.assertIn("field_count", self.code)
        self.assertIn("ApplySearchFilter", self.code)

    def test_exact_timeframe_quick_fields_are_visible(self):
        for name in (
            "DirectionQuickValue",
            "PullbackQuickValue",
            "TriggerQuickValue",
        ):
            self.assertIn(f'x:Name="{name}"', self.xaml)
            self.assertIn(f'"{name}"', self.code)

    def test_hard_safety_is_visible_and_locked(self):
        self.assertIn("REAL ACCOUNT LOCKED", self.xaml)
        self.assertIn("descriptor.LockedValue", self.code)
        self.assertIn("editor.IsEnabled = false", self.code)

    def test_full_field_groups_include_strategy_risk_execution_and_logging(self):
        for key in (
            '["timeframes"]',
            '["direction"]',
            '["pullback"]',
            '["trigger"]',
            '["risk"]',
            '["stop_loss"]',
            '["take_profit.dynamic"]',
            '["execution"]',
            '["safety"]',
            '["logging"]',
        ):
            with self.subTest(key=key):
                self.assertIn(key, self.code)


if __name__ == "__main__":
    unittest.main()
