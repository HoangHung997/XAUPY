"""Read-only probes; every status is derived from current runtime evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import os
import platform
import sys
import time
from typing import Any

from . import __version__
from .config_schema import validate_profile
from .contracts import PROTOCOL_VERSION
from .indicator_comparison import compare_indicators


def collect_diagnostics(server: Any) -> dict[str, Any]:
    bridge = server.bridge.status()
    fresh = server.bridge.market_data_connected()
    overview = server.bridge.overview_payload()
    errors = validate_profile(server.active_profile)
    checks = [
        {"name": "Python Engine", "status": "OK", "detail": f"Python {platform.python_version()} · PID {os.getpid()}"},
        {"name": "Local IPC", "status": "OK" if server._server is not None else "WAIT",
         "detail": f"{server.host}:{server.bound_port} · protocol v{PROTOCOL_VERSION}"},
        {"name": "EA Bridge", "status": "OK" if bridge.connected else "WAIT",
         "detail": f"{bridge.snapshots_total} snapshots · age {bridge.age_ms if bridge.age_ms is not None else '—'} ms"},
        {"name": "MT5 Terminal", "status": "OK" if bridge.connected and bridge.terminal_connected else "WAIT",
         "detail": bridge.account_trade_mode or "Chưa có tài khoản từ Bridge"},
        {"name": "Market data", "status": "OK" if fresh else "WAIT", "detail": "Fresh" if fresh else "Chờ snapshot mới"},
        {"name": "Active profile", "status": "OK" if not errors else "ERROR", "detail": "; ".join(errors) or "Canonical schema hợp lệ"},
        {"name": "Execution", "status": server.execution.status()['mode'], "detail": server.execution.status()['reason']},
        {"name": "Journal", "status": "OK" if not server.journal.invalid_replay_lines else "WARN",
         "detail": f"{server.journal.event_count} events · {server.journal.invalid_replay_lines} invalid replay lines"},
        {"name": "Startup recovery", "status": "WARN" if "rejected" in server.settings_store.recovery_message else "OK",
         "detail": server.settings_store.recovery_message},
    ]
    return {"checked_utc": datetime.now(timezone.utc).isoformat(), "checks": checks,
            "engine_version": __version__, "python_version": platform.python_version(),
            "platform": platform.platform(), "executable": sys.executable,
            "uptime_seconds": round(time.monotonic() - server._started_monotonic, 1),
            "bridge": bridge.to_payload(), "overview": overview,
            "broker_metadata": server.library.merge_calendar(server.bridge.latest_fresh_snapshot() or {}),
            "indicator_comparison":compare_indicators(server.bridge.latest_fresh_snapshot() or {},server.strategy.history),
            "strategy": server.strategy.status_payload(market_connected=fresh),
            "paths": {"state": str(server.settings_store.root_dir), "logs": str(server.journal.root_dir),
                      "backtests": str(server.backtests.root_dir), "backups": str(server.settings_store.backup_dir)},
            "execution":server.execution.status(),
            "trading_enabled":server.execution.status()['trading_enabled'], "execution_enabled":server.execution.status()['execution_enabled']}
