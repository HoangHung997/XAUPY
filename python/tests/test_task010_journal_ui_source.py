import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAIN_XAML = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml"
MAIN_CODE = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml.cs"
JOURNAL_XAML = ROOT / "src" / "XAUPY.Desktop" / "JournalDashboard.axaml"
JOURNAL_CODE = ROOT / "src" / "XAUPY.Desktop" / "JournalDashboard.axaml.cs"
SUPERVISOR = ROOT / "src" / "XAUPY.Ipc" / "EngineProcessSupervisor.cs"
MODEL = ROOT / "src" / "XAUPY.Ipc" / "JournalModels.cs"
REFERENCE = ROOT / "docs" / "ui-reference" / "Tab Nhật Kí.png"


class Task010JournalUiSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_xaml = MAIN_XAML.read_text(encoding="utf-8")
        cls.main_code = MAIN_CODE.read_text(encoding="utf-8")
        cls.xaml = JOURNAL_XAML.read_text(encoding="utf-8")
        cls.code = JOURNAL_CODE.read_text(encoding="utf-8")
        cls.supervisor = SUPERVISOR.read_text(encoding="utf-8")
        cls.model = MODEL.read_text(encoding="utf-8")

    def test_approved_reference_exists(self):
        self.assertTrue(REFERENCE.exists())
        self.assertGreater(REFERENCE.stat().st_size, 100_000)

    def test_journal_tab_is_real_full_width_host_not_placeholder(self):
        self.assertIn('x:Name="JournalDashboard"', self.main_xaml)
        self.assertIn('Grid.ColumnSpan="2"', self.main_xaml)
        self.assertIn('_journalDashboard.IsVisible = logs', self.main_code)
        self.assertIn('_journalDashboard.ApplySummary(e.JournalSummary)', self.main_code)
        self.assertIn('_journalDashboard.EnsureLoadedAsync(force: true)', self.main_code)

    def test_reference_source_filters_exist(self):
        for value in (
            "Tất cả",
            "MT5",
            "EA Bridge",
            "Python Engine",
            "Strategy",
            "Orders",
            "Alerts",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.xaml)

    def test_reference_level_search_date_actions_exist(self):
        for value in (
            "INFO",
            "WARN",
            "ERROR",
            "DEBUG",
            "Tìm kiếm trong nhật ký",
            "Hôm nay",
            "Tất cả thời gian",
            "Dấu trang",
            "Xuất log",
            "Làm mới",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.xaml)

    def test_reference_table_detail_and_right_rail_exist(self):
        for value in (
            "Thời gian",
            "Mức độ",
            "Nguồn",
            "Thông điệp",
            "Tag",
            "Chi tiết nhật ký",
            "Tổng quan nhật ký",
            "Cảnh báo gần đây",
            "Dấu trang (Bookmarks)",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.xaml)

    def test_journal_uses_engine_query_and_bookmark_ipc(self):
        self.assertIn("QueryJournalAsync", self.code)
        self.assertIn("SetJournalBookmarkAsync", self.code)
        self.assertIn("journal_query", self.supervisor)
        self.assertIn("journal_bookmark_set", self.supervisor)
        self.assertIn("JournalQueryResult", self.model)
        self.assertIn("JournalBookmarkResult", self.model)
        self.assertIn("JournalSummarySnapshot.FromHeartbeatPayload", self.supervisor)

    def test_runtime_rows_are_not_mocked_in_xaml(self):
        self.assertIn('x:Name="JournalRowsHost"', self.xaml)
        self.assertIn('x:Name="RecentAlertsHost"', self.xaml)
        self.assertIn('x:Name="BookmarksHost"', self.xaml)
        self.assertNotIn("Trade executed successfully", self.xaml)
        self.assertNotIn("Connection lost - retrying", self.xaml)
        self.assertNotIn("RSI entered oversold", self.xaml)

    def test_detail_is_structured_and_exported_from_real_query_rows(self):
        self.assertIn("item.Details", self.code)
        self.assertIn("item.CorrelationId", self.code)
        self.assertIn("item.ProfileHash", self.code)
        self.assertIn("JsonSerializer.Serialize", self.code)
        self.assertIn("_events.OrderBy", self.code)

    def test_task010_desktop_version_and_previous_execution_guards_remain(self):
        self.assertIn('desktop_version = "0.12.0-task012"', self.supervisor)
        self.assertIn("RejectUnexpectedExecutionEnable", self.supervisor)
        self.assertIn("RejectUnexpectedOrdersExecutionEnable", self.supervisor)
        self.assertIn("Task 012 manual action response violated simulation-only safety", self.supervisor)


if __name__ == "__main__":
    unittest.main()
