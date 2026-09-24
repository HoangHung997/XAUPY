from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args),
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config_exe")
    args = parser.parse_args()

    exe = str(Path(args.config_exe).resolve())

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        profile = root / "default.json"
        set_file = root / "default.set"
        imported = root / "imported.json"
        report = root / "report.json"

        result = run(exe, "defaults", "--out", str(profile))
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        result = run(exe, "validate", str(profile))
        if result.returncode != 0 or "VALID" not in result.stdout:
            raise RuntimeError(result.stderr or result.stdout)

        result = run(exe, "export-set", str(profile), "--out", str(set_file))
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        if not set_file.read_bytes().startswith(b"\xff\xfe"):
            raise RuntimeError("canonical .set is not UTF-16 LE BOM")

        result = run(
            exe,
            "import-set",
            str(set_file),
            "--out",
            str(imported),
            "--report",
            str(report),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        original = json.loads(profile.read_text(encoding="utf-8"))
        roundtrip = json.loads(imported.read_text(encoding="utf-8"))
        if original != roundtrip:
            raise RuntimeError("profile -> .set -> profile is not lossless")

        report_data = json.loads(report.read_text(encoding="utf-8"))
        if report_data["imported_count"] < 100:
            raise RuntimeError("too few canonical .set fields imported")

    print("PASS: packaged xaupy-config defaults/validate/export/import smoke test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
