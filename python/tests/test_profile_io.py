import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.config_schema import default_profile
from xaupy_engine.profile_io import load_profile, save_profile


class ProfileIoTests(unittest.TestCase):
    def test_save_then_load_profile(self):
        profile = default_profile()
        profile["profile"]["name"] = "A/B profile"
        profile["timeframes"]["direction"] = "H4"

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "profiles" / "test.json"
            save_profile(profile, path)
            loaded = load_profile(path)
            self.assertEqual(profile, loaded)

    def test_invalid_profile_is_not_saved(self):
        profile = default_profile()
        profile["execution"]["allow_real_account"] = True

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "bad.json"
            with self.assertRaises(ValueError):
                save_profile(profile, path)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
