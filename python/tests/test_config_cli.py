import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

PYTHON_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parent


class ConfigCliTests(unittest.TestCase):
    def run_cli(self, *args):
        env = dict(__import__("os").environ)
        env["PYTHONPATH"] = str(PYTHON_ROOT)
        return subprocess.run(
            [sys.executable, "-m", "xaupy_engine.config_cli", *map(str, args)],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_defaults_validate_and_set_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = pathlib.Path(directory)
            profile = directory / "default.json"
            set_file = directory / "default.set"
            imported = directory / "imported.json"
            report = directory / "report.json"

            self.assertEqual(0, self.run_cli("defaults", "--out", profile).returncode)
            result = self.run_cli("validate", profile)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("VALID", result.stdout)

            self.assertEqual(
                0,
                self.run_cli("export-set", profile, "--out", set_file).returncode,
            )
            self.assertTrue(set_file.read_bytes().startswith(b"\xff\xfe"))

            result = self.run_cli(
                "import-set",
                set_file,
                "--out",
                imported,
                "--report",
                report,
            )
            self.assertEqual(0, result.returncode, result.stderr)

            self.assertEqual(
                json.loads(profile.read_text(encoding="utf-8")),
                json.loads(imported.read_text(encoding="utf-8")),
            )
            report_data = json.loads(report.read_text(encoding="utf-8"))
            self.assertGreaterEqual(report_data["imported_count"], 100)


if __name__ == "__main__":
    unittest.main()
