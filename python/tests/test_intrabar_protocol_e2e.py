import asyncio
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "scripts"))
from smoke_intrabar_engine import exercise_intrabar
from xaupy_engine.contracts import Envelope
from xaupy_engine.server import EngineServer


class IntrabarSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_socket_tick_lifecycle_keeps_broker_execution_locked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = EngineServer(port=0, state_dir=root / "state", journal_dir=root / "logs",
                                  backtest_dir=root / "backtests", optimizer_dir=root / "optimizer")
            await server.start()
            reader, writer = await asyncio.open_connection("127.0.0.1", server.bound_port)
            try:
                async def request(kind, payload=None, expected=None):
                    message = Envelope.create(kind, payload or {})
                    writer.write((message.to_json() + "\n").encode())
                    await writer.drain()
                    reply = Envelope.from_json((await asyncio.wait_for(reader.readline(), 3)).decode().strip())
                    self.assertEqual(message.request_id, reply.request_id)
                    self.assertEqual(expected or ("config_active_ack" if kind == "config_active_get" else kind + "_ack"), reply.type)
                    self.assertIs(reply.payload["trading_enabled"], False)
                    self.assertIs(reply.payload["execution_enabled"], False)
                    self.assertIsNone(reply.payload.get("command"))
                    return reply.payload
                self.assertEqual(16, await exercise_intrabar(request))
            finally:
                writer.close()
                await writer.wait_closed()
                await server.close()


if __name__ == "__main__":
    unittest.main()
