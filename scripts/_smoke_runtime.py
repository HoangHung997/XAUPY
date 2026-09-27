"""Keep packaged smoke processes away from the user's persistent XAUPY data."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile


_temporary_runtime: tempfile.TemporaryDirectory[str] | None = None


def isolated_environment(
    root: Path | None = None,
    *,
    journal_dir: Path | None = None,
    backtest_dir: Path | None = None,
    optimizer_dir: Path | None = None,
) -> dict[str, str]:
    """Reuse one temporary root for intentional restarts in the same smoke run.

    Explicit roots must be inside a smoke script's TemporaryDirectory scope.
    The helper only creates directories; it never removes existing user data.
    """
    global _temporary_runtime
    if root is None:
        if _temporary_runtime is None:
            _temporary_runtime = tempfile.TemporaryDirectory(prefix="xaupy-smoke-runtime-")
        root = Path(_temporary_runtime.name)
    root = root.resolve()
    paths = {
        "XAUPY_STATE_DIR": root / "state",
        "XAUPY_LOG_DIR": journal_dir if journal_dir is not None else root / "logs",
        "XAUPY_BACKTEST_DIR": backtest_dir if backtest_dir is not None else root / "backtests",
        "XAUPY_OPTIMIZER_DIR": optimizer_dir if optimizer_dir is not None else root / "optimizer",
    }
    env = dict(os.environ)
    for name, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        env[name] = str(path.resolve())
    return env
