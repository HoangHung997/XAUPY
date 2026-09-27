from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xaupy_engine.contracts import Envelope
from xaupy_engine.server import EngineServer
from xaupy_engine.settings import SettingsStore, default_settings, validate_settings


class SettingsRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SettingsStore(self.temp.name)

    def test_settings_and_profile_survive_restart(self):
        settings = default_settings()
        settings["startup"]["auto_restart_engine"] = False
        profile = deepcopy(self.store.profile)
        profile["profile"]["name"] = "Restart proof"
        self.store.save(settings=settings, profile=profile)
        restarted = SettingsStore(self.temp.name)
        self.assertFalse(restarted.settings["startup"]["auto_restart_engine"])
        self.assertEqual("Restart proof", restarted.profile["profile"]["name"])
        self.assertIn("reconciliation", restarted.recovery_message)

    def test_engine_instance_identity_captured_at_startup(self):
        with patch.dict("os.environ", {"XAUPY_INSTANCE_ID": "owned-process-123"}):
            server = EngineServer(port=0, journal_dir=Path(self.temp.name) / "logs", state_dir=self.temp.name)
        self.assertEqual("owned-process-123", server._common()["engine_instance_id"])

    def test_corrupt_state_falls_back_and_preserves_evidence(self):
        self.store.path.write_text("{incomplete", encoding="utf-8")
        restarted = SettingsStore(self.temp.name)
        self.assertEqual(default_settings(), restarted.settings)
        self.assertIn("rejected", restarted.recovery_message)
        self.assertEqual("{incomplete", self.store.path.read_text(encoding="utf-8"))

    def test_atomic_write_failure_keeps_previous_state(self):
        self.store.save()
        before = self.store.path.read_bytes()
        changed = deepcopy(self.store.settings)
        changed["startup"]["auto_start_engine"] = False
        with patch("xaupy_engine.settings.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError): self.store.save(settings=changed)
        self.assertEqual(before, self.store.path.read_bytes())
        self.assertTrue(self.store.settings["startup"]["auto_start_engine"])

    def test_fail_safe_flags_cannot_be_unlocked(self):
        for name, baseline in default_settings()["safety"].items():
            changed = default_settings()
            changed["safety"][name] = not baseline
            self.assertTrue(validate_settings(changed), name)
            with self.assertRaises(ValueError): self.store.save(settings=changed)

    def test_unknown_schema_and_remote_ipc_rejected(self):
        for group, field, value in [("connection", "host", "0.0.0.0"), ("connection", "port", 5000), ("backup", "keep_count", True)]:
            changed = default_settings(); changed[group][field] = value
            self.assertTrue(validate_settings(changed))
        changed = default_settings(); changed["password"] = "secret"
        self.assertTrue(validate_settings(changed))

    def test_restore_validates_before_mutation_and_keeps_prior_backup(self):
        self.store.save()
        backup = self.store.create_backup()
        changed = deepcopy(self.store.profile); changed["profile"]["name"] = "Changed"
        self.store.save(profile=changed)
        self.store.restore_backup(backup["id"])
        self.assertNotEqual("Changed", self.store.profile["profile"]["name"])
        self.assertGreaterEqual(len(self.store.list_backups()), 3)
        file = self.store.backup_dir / backup["id"]
        document = json.loads(file.read_text(encoding="utf-8"))
        document["settings"]["safety"]["allow_real_account"] = True
        file.write_text(json.dumps(document), encoding="utf-8")
        before = self.store.path.read_bytes()
        with self.assertRaises(ValueError): self.store.restore_backup(backup["id"])
        self.assertEqual(before, self.store.path.read_bytes())

    def test_backup_traversal_rejected_and_retention_bounded(self):
        for name in ["../runtime-v1.json", "xaupy-../../runtime-v1.json", "runtime-v1.json", None]:
            with self.assertRaises(ValueError): self.store.restore_backup(name)
        changed = default_settings(); changed["backup"]["keep_count"] = 2
        self.store.save(settings=changed)
        for _ in range(5): self.store.create_backup()
        self.assertEqual(2, len(self.store.list_backups()))
        self.assertTrue(self.store.path.is_file())


class MaintenanceProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.server = EngineServer(port=0, state_dir=root / "state", journal_dir=root / "logs", backtest_dir=root / "backtests", optimizer_dir=root / "optimizer")
        await self.server.start()
        self.reader, self.writer = await asyncio.open_connection("127.0.0.1", self.server.bound_port)

    async def asyncTearDown(self):
        self.writer.close(); await self.writer.wait_closed()
        await self.server.close()
        self.temp.cleanup()

    async def exchange(self, kind, payload=None):
        request = Envelope.create(kind, payload or {})
        self.writer.write((request.to_json() + "\n").encode()); await self.writer.drain()
        result = Envelope.from_json((await asyncio.wait_for(self.reader.readline(), 2)).decode())
        self.assertEqual(request.request_id, result.request_id)
        self.assertEqual(kind + "_ack", result.type)
        self.assertFalse(result.payload["execution_enabled"])
        self.assertFalse(result.payload["trading_enabled"])
        return result.payload

    async def test_diagnostics_reports_absent_bridge_honestly(self):
        result = await self.exchange("diagnostics_get")
        self.assertTrue(result["ok"])
        checks = {c["name"]: c for c in result["diagnostics"]["checks"]}
        self.assertEqual("OK", checks["Local IPC"]["status"])
        self.assertEqual("WAIT", checks["EA Bridge"]["status"])
        self.assertEqual("WAIT", checks["Market data"]["status"])
        self.assertEqual("LOCKED", checks["Execution Guardian"]["status"])

    async def test_settings_validation_backup_restore_wire_contract(self):
        result = await self.exchange("settings_get")
        settings = result["settings"]
        settings["startup"]["auto_restart_engine"] = False
        saved = await self.exchange("settings_set", {"settings": settings})
        self.assertTrue(saved["ok"])
        backup = await self.exchange("backup_create")
        self.assertTrue(backup["ok"])
        settings["startup"]["auto_restart_engine"] = True
        await self.exchange("settings_set", {"settings": settings})
        restored = await self.exchange("backup_restore", {"backup_id": backup["backup"]["id"]})
        self.assertTrue(restored["ok"])
        self.assertFalse(restored["settings"]["startup"]["auto_restart_engine"])
        self.assertEqual("BACKUP_RESTORED", self.server.strategy.status_payload(market_connected=False)["last_reset_reason"])
        rejected = await self.exchange("settings_set", {"settings": {"unsafe": True}})
        self.assertFalse(rejected["ok"])
        rejected = await self.exchange("backup_restore", {"backup_id": "../runtime-v1.json"})
        self.assertFalse(rejected["ok"])

    async def test_invalid_settings_type_rejected(self):
        for value in [None, "settings", [], True]:
            result = await self.exchange("settings_set", {"settings": value})
            self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
