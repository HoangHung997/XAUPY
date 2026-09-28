import asyncio
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import Mock
from uuid import uuid4

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))
from xaupy_engine.contracts import Envelope, ProtocolError
from xaupy_engine.server import EngineServer
from test_strategy_protocol import bridge_snapshot, exchange
from smoke_demo_once_engine import exercise_demo_once


class DemoOnceProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = EngineServer(port=0, state_dir=self.temp.name)
        await self.server.start()
        self.writers = []
        self.session = str(uuid4())

    async def asyncTearDown(self):
        for writer in self.writers:
            writer.close()
        await asyncio.gather(*(w.wait_closed() for w in self.writers), return_exceptions=True)
        await self.server.close()
        self.temp.cleanup()

    async def connect(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.server.bound_port)
        self.writers.append(writer)
        return reader, writer

    def hello(self, session=None):
        return {"bridge_version": "1.017", "component": "mt5-bridge", "symbol": "XAUUSD",
                "demo_once_capable": True, "bridge_session_id": session or self.session}

    async def test_arm_without_capable_connection_is_rejected_before_controller(self):
        self.server.demo_once.arm = Mock()
        reader, writer = await self.connect()
        reply = await exchange(reader, writer, "demo_once_arm", {"confirmed": True})
        self.assertFalse(reply.payload["accepted"])
        self.assertEqual("BRIDGE_SESSION_REQUIRED", reply.payload["demo_once"]["code"])
        self.server.demo_once.arm.assert_not_called()

    async def test_real_strategy_signal_drives_only_one_isolated_demo_command(self):
        reader, writer = await self.connect()
        async def request(kind, payload=None):
            reply = await exchange(reader, writer, kind, payload)
            self.assertEqual("config_active_ack" if kind == "config_active_get" else kind + "_ack", reply.type)
            self.assertFalse(reply.payload["execution_enabled"])
            return reply.payload
        self.assertEqual(16, await exercise_demo_once(request))

    async def test_stale_authorization_lock_preserves_monitoring_and_blocks_arm(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = pathlib.Path(directory) / "demo-once-v1.lock"
            lock.write_bytes(b"crash evidence")
            server = EngineServer(port=0, state_dir=directory)
            await server.start()
            reader, writer = await asyncio.open_connection("127.0.0.1", server.bound_port)
            try:
                await exchange(reader, writer, "bridge_hello", self.hello())
                heartbeat = await exchange(reader, writer, "heartbeat")
                self.assertEqual("UNKNOWN", heartbeat.payload["demo_once"]["state"])
                self.assertTrue(heartbeat.payload["demo_once"]["budget_consumed"])
                reply = await exchange(reader, writer, "demo_once_arm", {"confirmed": True})
                self.assertFalse(reply.payload["accepted"])
                self.assertEqual(b"crash evidence", lock.read_bytes())
            finally:
                writer.close()
                await writer.wait_closed()
                await server.close()

    async def test_desktop_cannot_report_fill_or_take_bridge_ownership(self):
        ea_reader, ea_writer = await self.connect()
        hello = await exchange(ea_reader, ea_writer, "bridge_hello", self.hello())
        self.assertEqual("bridge_hello_ack", hello.type)
        reader, writer = await self.connect()
        self.server.demo_once.record_result = Mock()
        for kind, payload in (("bridge_demo_once_result", {"bridge_session_id": self.session}),
                              ("bridge_hello", self.hello(str(uuid4()))),
                              ("bridge_hello", {"bridge_version": "legacy"})):
            reply = await exchange(reader, writer, kind, payload)
            self.assertEqual("error", reply.type)
        self.server.demo_once.record_result.assert_not_called()
        heartbeat = await exchange(reader, writer, "heartbeat")
        self.assertFalse(heartbeat.payload["execution_enabled"])
        self.assertIn("demo_once", heartbeat.payload)

    async def test_command_only_in_matching_owner_snapshot_reply(self):
        reader, writer = await self.connect()
        await exchange(reader, writer, "bridge_hello", self.hello())
        snapshot = bridge_snapshot(1, 2300, 2300, 2300)
        snapshot.update(bridge_session_id=self.session, demo_once_capable=True)
        command = {"kind": "DEMO_ONE_SHOT_MARKET", "attempt_id": str(uuid4())}
        self.server.demo_once.on_signal = Mock(return_value=command)
        reply = await exchange(reader, writer, "bridge_snapshot", snapshot)
        self.assertEqual(command, reply.payload["demo_once_command"])
        self.assertIsNone(reply.payload["command"])
        self.assertFalse(reply.payload["execution_enabled"])
        self.server.demo_once.on_signal.assert_called_once()
        self.server.demo_once.on_signal.reset_mock()
        snapshot["bridge_session_id"] = str(uuid4())
        rejected = await exchange(reader, writer, "bridge_snapshot", snapshot)
        self.assertEqual("error", rejected.type)
        self.server.demo_once.on_signal.assert_not_called()

    async def test_legacy_snapshot_cannot_dispatch_demo_command(self):
        self.server.demo_once.on_signal = Mock()
        reader, writer = await self.connect()
        await exchange(reader, writer, "bridge_hello", {"bridge_version": "legacy"})
        reply = await exchange(reader, writer, "bridge_snapshot", bridge_snapshot(1, 2300, 2300, 2300))
        self.assertIsNone(reply.payload["demo_once_command"])
        self.server.demo_once.on_signal.assert_not_called()

    async def test_owning_connection_result_requires_same_session(self):
        reader, writer = await self.connect()
        await exchange(reader, writer, "bridge_hello", self.hello())
        self.server.demo_once.record_result = Mock(return_value={"accepted": True, "state": "UNKNOWN"})
        rejected = await exchange(reader, writer, "bridge_demo_once_result", {"bridge_session_id": str(uuid4())})
        self.assertFalse(rejected.payload["accepted"])
        self.server.demo_once.record_result.assert_not_called()
        accepted = await exchange(reader, writer, "bridge_demo_once_result", {"bridge_session_id": self.session})
        self.assertTrue(accepted.payload["accepted"])
        self.server.demo_once.record_result.assert_called_once()

    def test_duplicate_json_fields_cannot_change_authorization_meaning(self):
        raw = Envelope.create("demo_once_arm", {"confirmed": False}).to_json()
        raw = raw.replace('"confirmed":false', '"confirmed":false,"confirmed":true')
        with self.assertRaisesRegex(ProtocolError, "duplicate JSON field"):
            Envelope.from_json(raw)

    def test_restart_result_reconciliation_requires_current_and_original_identity(self):
        original = str(uuid4())
        identity = {"account_login": 12345, "account_server": "Isolated-Demo", "symbol": "XAUUSD", "magic": 991188}
        auth = {**identity, "attempt_id": str(uuid4()), "bridge_session_id": original}
        self.server.demo_once.status = Mock(return_value={"authorization": auth})
        self.server.bridge.latest_fresh_snapshot = Mock(return_value={**identity,
            "bridge_session_id": self.session, "account_trade_mode": "DEMO", "demo_once_capable": True})
        self.assertTrue(self.server._demo_result_session_matches(auth, self.session))
        self.assertFalse(self.server._demo_result_session_matches(auth, None))
        self.assertFalse(self.server._demo_result_session_matches({**auth, "account_login": 456}, self.session))
        self.assertFalse(self.server._demo_result_session_matches({**auth, "attempt_id": str(uuid4())}, self.session))
        self.assertFalse(self.server._demo_result_session_matches({**auth, "bridge_session_id": str(uuid4())}, self.session))
        self.server.bridge.latest_fresh_snapshot.return_value["account_trade_mode"] = "REAL"
        self.assertFalse(self.server._demo_result_session_matches(auth, self.session))


if __name__ == "__main__":
    unittest.main()
