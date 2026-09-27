from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HELPER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "_smoke_runtime.py"
spec = importlib.util.spec_from_file_location("xaupy_smoke_runtime_test", HELPER_PATH)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class PackagedSmokeIsolationTests(unittest.TestCase):
    def test_all_persistent_directories_override_inherited_user_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            user_root = root / "user-state"
            user_root.mkdir()
            sentinel = user_root / "runtime-v1.json"
            sentinel.write_text('{"user_profile":"must remain untouched"}', encoding="utf-8")
            names = ("XAUPY_STATE_DIR", "XAUPY_LOG_DIR", "XAUPY_BACKTEST_DIR", "XAUPY_OPTIMIZER_DIR")
            with patch.dict(os.environ, {name: str(user_root) for name in names}):
                environment = runtime.isolated_environment(root / "smoke")
                for name in names:
                    # Windows runners may expose TEMP through an 8.3 alias or junction.
                    # Compare canonical paths, as the runtime helper does when exporting them.
                    self.assertTrue(Path(environment[name]).resolve().is_relative_to((root / "smoke").resolve()))
                    self.assertTrue(Path(environment[name]).is_dir())
                    self.assertEqual(str(user_root), os.environ[name])
            self.assertEqual('{"user_profile":"must remain untouched"}', sentinel.read_text(encoding="utf-8"))
            self.assertEqual([sentinel], list(user_root.iterdir()))

    def test_restart_reuses_its_temp_state_but_different_fixture_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = runtime.isolated_environment(root / "first")
            marker = Path(first["XAUPY_STATE_DIR"]) / "restart-evidence.json"
            marker.write_text("preserved", encoding="utf-8")
            restarted = runtime.isolated_environment(root / "first")
            unrelated = runtime.isolated_environment(root / "second")
            self.assertEqual(first, restarted)
            self.assertEqual("preserved", marker.read_text(encoding="utf-8"))
            self.assertNotEqual(first["XAUPY_STATE_DIR"], unrelated["XAUPY_STATE_DIR"])
            self.assertFalse((Path(unrelated["XAUPY_STATE_DIR"]) / marker.name).exists())


if __name__ == "__main__":
    unittest.main()
