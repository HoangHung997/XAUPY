"""Validated local settings, crash-safe profile persistence and bounded backups."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4

from .config_schema import default_profile, normalized_profile, validate_profile


def default_state_directory() -> Path:
    override = os.environ.get("XAUPY_STATE_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "XAUPY/state"
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "xaupy/state"


def default_settings() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "startup": {"auto_start_engine": True, "auto_restart_engine": True, "start_with_windows": False},
        "connection": {"mt5_path": "", "host": "127.0.0.1", "port": 39421},
        "appearance": {"theme": "N30 Dark", "language": "Tiếng Việt", "font_scale": 100},
        "notifications": {"system_errors": True, "connection_changes": True},
        "backup": {"auto_backup": True, "keep_count": 30},
        "safety": {"block_new_entries_on_disconnect": True, "preserve_server_stops": True,
                   "require_reconciliation": True, "allow_real_account": False, "auto_start_trading": False},
    }


def validate_settings(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["settings must be an object"]
    errors: list[str] = []
    defaults = default_settings()
    if set(value) != set(defaults):
        errors.append("settings sections do not match schema v1")
    for group, expected in defaults.items():
        actual = value.get(group)
        if not isinstance(expected, dict):
            if type(actual) is not int or actual != expected:
                errors.append(f"{group} must be {expected}")
            continue
        if not isinstance(actual, dict) or set(actual) != set(expected):
            errors.append(f"{group} fields do not match schema v1")
            continue
        for key, baseline in expected.items():
            item = actual[key]
            if type(item) is not type(baseline):
                errors.append(f"{group}.{key} has invalid type")
            elif group == "safety" and key not in {"allow_real_account", "auto_start_trading", "require_reconciliation"} and item != baseline:
                errors.append(f"{group}.{key} is safety locked")
    connection = value.get("connection", {})
    if isinstance(connection, dict):
        if connection.get("host") != "127.0.0.1":
            errors.append("Bridge host must be loopback 127.0.0.1")
        if type(connection.get('port')) is not int or not 1024<=connection['port']<=65535:
            errors.append('Bridge port must be 1024..65535')
        path = connection.get("mt5_path")
        if isinstance(path, str) and (len(path) > 1024 or any(c in path for c in "\r\n\0")):
            errors.append("MT5 path is invalid")
    appearance = value.get("appearance", {})
    if isinstance(appearance,dict):
        if appearance.get('theme') not in ('N30 Dark','N30 Contrast'):errors.append('Unknown appearance theme')
        if appearance.get('language') not in ('Tiếng Việt','English'):errors.append('Unknown appearance language')
        if type(appearance.get('font_scale')) is not int or not 90<=appearance['font_scale']<=150:errors.append('Font scale must be 90..150')
    backup = value.get("backup", {})
    if isinstance(backup, dict) and (type(backup.get("keep_count")) is not int or not 1 <= backup["keep_count"] <= 100):
        errors.append("backup.keep_count must be 1..100")
    return errors


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".xaupy-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class SettingsStore:
    def __init__(self, root_dir: str | os.PathLike[str] | None = None) -> None:
        self.root_dir = Path(root_dir) if root_dir is not None else default_state_directory()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.root_dir / "runtime-v1.json"
        self.backup_dir = self.root_dir / "backups"
        self.settings = default_settings()
        self.profile = default_profile()
        self.retention_warning = ""
        self.recovery_message = "Cài đặt mới; chưa chọn chế độ giao dịch"
        if self.path.exists():
            try:
                settings, profile = self._validate_document(self._read(self.path))
                self.settings, self.profile = settings, profile
                self.recovery_message = "Persisted settings and profile restored; awaiting fresh Bridge reconciliation"
            except (OSError, ValueError, TypeError, KeyError) as exc:
                self.recovery_message = f"Saved state rejected; safe defaults loaded: {exc}"
                # Preserve damaged evidence without overwriting it during startup.

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("State file exceeds 2 MiB")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _validate_document(doc: object) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(doc, dict) or doc.get("schema_version") != 1:
            raise ValueError("Unsupported backup/state schema")
        settings, profile = doc.get("settings"), doc.get("profile")
        errors = validate_settings(settings)
        if not isinstance(profile, dict):
            errors.append("profile must be an object")
        else:
            errors.extend(validate_profile(profile))
        if errors:
            raise ValueError("; ".join(errors))
        return deepcopy(settings), normalized_profile(profile)

    def document(self) -> dict[str, Any]:
        return {"schema_version": 1, "settings": deepcopy(self.settings), "profile": deepcopy(self.profile)}

    def save(self, *, settings: dict[str, Any] | None = None, profile: dict[str, Any] | None = None) -> None:
        candidate = {"schema_version": 1, "settings": settings if settings is not None else self.settings,
                     "profile": profile if profile is not None else self.profile}
        accepted_settings, accepted_profile = self._validate_document(candidate)
        if self.settings["backup"]["auto_backup"] and self.path.exists():
            self.create_backup()
        _atomic_json(self.path, {"schema_version": 1, "settings": accepted_settings, "profile": accepted_profile})
        self.settings, self.profile = accepted_settings, accepted_profile
        self._prune()

    def create_backup(self) -> dict[str, Any]:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = f"xaupy-{stamp}-{uuid4().hex[:8]}.json"
        path = self.backup_dir / name
        doc = self.document()
        doc["created_utc"] = datetime.now(timezone.utc).isoformat()
        _atomic_json(path, doc)
        self._prune()
        return {"id": name, "path": str(path), "bytes": path.stat().st_size}

    def _prune(self) -> None:
        self.retention_warning = ""
        try:
            files = sorted(self.backup_dir.glob("xaupy-*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
            for path in files[self.settings["backup"]["keep_count"]:]:
                # Only remove our own generated regular files in the exact backup directory.
                if path.is_file() and not path.is_symlink() and path.resolve().parent == self.backup_dir.resolve():
                    path.unlink()
        except OSError as exc:
            # The new backup/state is already committed; report cleanup separately.
            self.retention_warning = f"Backup saved, but retention cleanup failed: {exc}"

    def list_backups(self) -> list[dict[str, Any]]:
        return [{"id": p.name, "bytes": p.stat().st_size,
                 "modified_utc": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()}
                for p in sorted(self.backup_dir.glob("xaupy-*.json"), key=lambda p: p.name, reverse=True)
                if p.is_file() and not p.is_symlink()]

    def restore_backup(self, backup_id: object) -> None:
        if not isinstance(backup_id, str) or Path(backup_id).name != backup_id or not backup_id.startswith("xaupy-"):
            raise ValueError("Invalid backup id")
        path = self.backup_dir / backup_id
        if path.is_symlink() or path.resolve().parent != self.backup_dir.resolve():
            raise ValueError("Backup must belong to XAUPY backup directory")
        settings, profile = self._validate_document(self._read(path))
        self.create_backup()
        _atomic_json(self.path, {"schema_version": 1, "settings": settings, "profile": profile})
        self.settings, self.profile = settings, profile
        self._prune()
        self.recovery_message = "Đã khôi phục và đặt lại chiến lược; quyền giao dịch theo cài đặt đã lưu"

    def payload(self) -> dict[str, Any]:
        return {"settings": deepcopy(self.settings), "state_path": str(self.path),
                "backup_path": str(self.backup_dir), "backups": self.list_backups(),
                "recovery_message": self.recovery_message, "retention_warning": self.retention_warning}
