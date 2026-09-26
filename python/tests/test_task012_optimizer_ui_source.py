import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAIN_XAML = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml"
MAIN_CODE = ROOT / "src" / "XAUPY.Desktop" / "MainWindow.axaml.cs"
OPT_XAML = ROOT / "src" / "XAUPY.Desktop" / "OptimizerDashboard.axaml"
OPT_CODE = ROOT / "src" / "XAUPY.Desktop" / "OptimizerDashboard.axaml.cs"
SUPERVISOR = ROOT / "src" / "XAUPY.Ipc" / "EngineProcessSupervisor.cs"
MODEL = ROOT / "src" / "XAUPY.Ipc" / "OptimizerModels.cs"
SPEC = ROOT / "docs" / "TASK012_OPTIMIZER_WALK_FORWARD_SPEC.md"
REFERENCE = ROOT / "docs" / "ui-reference" / "Tab Tối Ưu.png"


class Task012OptimizerUiSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_xaml = MAIN_XAML.read_text(encoding="utf-8")
        cls.main_code = MAIN_CODE.read_text(encoding="utf-8")
        cls.xaml = OPT_XAML.read_text(encoding="utf-8")
        cls.code = OPT_CODE.read_text(encoding="utf-8")
        cls.supervisor = SUPERVISOR.read_text(encoding="utf-8")
        cls.model = MODEL.read_text(encoding="utf-8")
        cls.spec = SPEC.read_text(encoding="utf-8")

    def test_reference_exists_and_is_primary_source(self):
        self.assertTrue(REFERENCE.exists())
        self.assertGreater(REFERENCE.stat().st_size, 100_000)
        self.assertIn("docs/ui-reference/README.md", self.spec)
        self.assertIn("Tab Tối Ưu.png", self.spec)

    def test_optimizer_is_real_host_with_live_sidebar(self):
        self.assertIn('x:Name="OptimizerDashboard"', self.main_xaml)
        self.assertIn('Grid.Column="1"', self.main_xaml)
        self.assertIn('_optimizerDashboard.IsVisible = optimization', self.main_code)
        self.assertIn(
            'liveSidebar = overview || strategy || monitoring || backtest || optimization',
            self.main_code,
        )
        self.assertIn('_optimizerDashboard.EnsureLoadedAsync(force: true)', self.main_code)
        self.assertIn('_optimizerDashboard.ApplyStatus(e.OptimizerStatus)', self.main_code)

    def test_reference_information_zones_exist(self):
        for value in (
            "Tối ưu chiến lược - Parameter Sweep",
            "Phạm vi tham số tối ưu",
            "Trạng thái tối ưu",
            "Tài nguyên tính toán",
            "Top 10 bộ tham số tốt nhất",
            "Heatmap kết quả tối ưu",
            "Walk-Forward Validation",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.xaml)

    def test_reference_actions_and_walk_forward_controls_exist(self):
        for value in (
            "Lưu preset",
            "Tải preset",
            "BẮT ĐẦU TỐI ƯU",
            "DỪNG",
            "CHẠY WALK-FORWARD",
            "Số giai đoạn (folds)",
            "Tỷ lệ train / test",
            "Bước trượt (rolling)",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.xaml)

    def test_results_are_real_data_hosts_not_mock_numbers(self):
        for name in (
            "TopSetupRowsHost",
            "HeatmapGridHost",
            "WalkForwardFoldHost",
            "OptimizerProgressBar",
        ):
            self.assertIn(f'x:Name="{name}"', self.xaml)
            self.assertIn(f'"{name}"', self.code)

        for mock_value in (
            "147,200.00",
            "78.50%",
            "18.45",
            "89.2%",
            "67.8%",
        ):
            self.assertNotIn(mock_value, self.xaml)

    def test_system_resource_metrics_are_not_fabricated(self):
        self.assertIn("Task 014 diagnostics", self.xaml)
        self.assertIn("Worker slots", self.xaml)
        self.assertIn("Throughput", self.xaml)
        self.assertNotIn("CPU 68%", self.xaml)
        self.assertNotIn("RAM 6.2", self.xaml)

    def test_ui_uses_typed_optimizer_ipc(self):
        for method in (
            "StartOptimizerAsync",
            "StartWalkForwardAsync",
            "QueryOptimizerStatusAsync",
            "CancelOptimizerAsync",
            "GetOptimizerResultAsync",
            "GetOptimizerHeatmapAsync",
            "QueryOptimizerHistoryAsync",
            "DeleteOptimizerResultAsync",
        ):
            with self.subTest(method=method):
                self.assertIn(method, self.supervisor)

        for name in (
            "OptimizerStatusSnapshot",
            "OptimizerCandidateSnapshot",
            "OptimizerHeatmapSnapshot",
            "WalkForwardFoldSnapshot",
            "WalkForwardAggregateSnapshot",
        ):
            with self.subTest(name=name):
                self.assertIn(name, self.model)

    def test_train_only_leakage_evidence_is_visible(self):
        self.assertIn("TRAIN_ONLY", self.code)
        self.assertIn("train/test không overlap", self.code)
        self.assertIn("LeakageGuardPassed", self.code)
        self.assertIn("selection_source = TRAIN_ONLY", self.spec)

    def test_heatmap_is_backend_driven_without_interpolation(self):
        self.assertIn("GetOptimizerHeatmapAsync", self.code)
        self.assertIn("Samples", self.code)
        self.assertIn("No synthetic interpolation", self.spec)

    def test_cost_assumptions_are_explicit_for_reproducibility(self):
        for name in (
            "OptimizeBalanceBox",
            "OptimizeSpreadBox",
            "OptimizeCommissionBox",
            "MinTradesBox",
            "WorkersBox",
        ):
            self.assertIn(f'x:Name="{name}"', self.xaml)
            self.assertIn(f'"{name}"', self.code)

    def test_task012_version_and_safety_guards_remain(self):
        self.assertIn('desktop_version = "0.13.0-task013"', self.supervisor)
        self.assertIn("RejectUnexpectedExecutionEnable", self.supervisor)
        self.assertIn("RejectUnexpectedOrdersExecutionEnable", self.supervisor)
        self.assertIn(
            "Task 013 manual action response violated simulation-only safety",
            self.supervisor,
        )


if __name__ == "__main__":
    unittest.main()
