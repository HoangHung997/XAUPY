import asyncio
import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.config_schema import TIMEFRAME_OPTIONS
from xaupy_engine.contracts import Envelope
from xaupy_engine.server import EngineServer


async def exchange(reader, writer, message_type, payload=None):
    request = Envelope.create(message_type, payload or {})
    writer.write((request.to_json() + "\n").encode("utf-8"))
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=2)
    response = Envelope.from_json(line.decode("utf-8").rstrip("\r\n"))
    if response.request_id != request.request_id:
        raise AssertionError("response request_id mismatch")
    return response


def bridge_snapshot(index, direction_close, pullback_close, trigger_close, *, connected=True):
    selected = {
        "M30": direction_close,
        "M5": pullback_close,
        "M1": trigger_close,
    }
    timestamp = 1_800_100_000 + (index * 60)
    bars = {}
    for timeframe in TIMEFRAME_OPTIONS:
        close = float(selected.get(timeframe, trigger_close))
        bars[timeframe] = {
            "time": timestamp,
            "open": close - 0.1,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "tick_volume": 100 + index,
        }

    return {
        "bridge_version": "0.3.0-task003",
        "symbol": "XAUUSD",
        "terminal_connected": connected,
        "account_trade_mode": "DEMO",
        "bid": float(trigger_close),
        "ask": float(trigger_close) + 0.2,
        "guardian": {
            "execution_locked": True,
            "execution_ready": False,
            "reason": "TASK003_EXECUTION_LOCKED",
        },
        "bars": bars,
    }


def fast_profile(profile):
    changed = copy.deepcopy(profile)
    changed["profile"]["name"] = "Task007 Deterministic"
    changed["direction"]["ma_period"] = 3
    changed["pullback"]["rsi_period"] = 2
    changed["pullback"]["rsi_buy_level"] = 40.0
    changed["pullback"]["rsi_sell_level"] = 60.0
    changed["pullback"]["z_enabled"] = False
    changed["trigger"]["rsi_period"] = 2
    changed["trigger"]["rsi_reversal_delta"] = 10.0
    changed["trigger"]["z_enabled"] = False
    changed["filters"]["adx"]["enabled"] = False
    changed["filters"]["atr"]["enabled"] = False
    changed["filters"]["open"]["enabled"] = False
    changed["direction"]["open_filter_enabled"] = False
    return changed


class StrategyProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = EngineServer(port=0)
        await self.server.start()
        self.reader, self.writer = await asyncio.open_connection(
            "127.0.0.1", self.server.bound_port
        )

    async def asyncTearDown(self):
        self.writer.close()
        await self.writer.wait_closed()
        await self.server.close()

    async def test_heartbeat_exposes_stale_strategy_without_enabling_execution(self):
        heartbeat = await exchange(self.reader, self.writer, "heartbeat")
        strategy = heartbeat.payload["strategy"]

        self.assertFalse(strategy["available"])
        self.assertFalse(strategy["ready"])
        self.assertEqual("STALE", strategy["state"])
        self.assertFalse(strategy["trading_enabled"])
        self.assertFalse(strategy["execution_enabled"])
        self.assertFalse(heartbeat.payload["trading_enabled"])
        self.assertFalse(heartbeat.payload["execution_enabled"])

    async def test_bridge_snapshots_drive_deterministic_buy_state(self):
        active = await exchange(self.reader, self.writer, "config_active_get")
        profile = fast_profile(active.payload["profile"])
        applied = await exchange(
            self.reader, self.writer, "config_active_set", {"profile": profile}
        )
        self.assertTrue(applied.payload["applied"])

        direction = [100, 101, 102, 103, 104, 105]
        pullback = [100, 99, 98, 97, 96, 95]
        trigger = [100, 99, 98, 97, 96, 98]

        states = []
        for index in range(len(direction)):
            response = await exchange(
                self.reader,
                self.writer,
                "bridge_snapshot",
                bridge_snapshot(
                    index,
                    direction[index],
                    pullback[index],
                    trigger[index],
                ),
            )
            self.assertEqual("bridge_snapshot_ack", response.type)
            strategy = response.payload["strategy"]
            states.append(strategy["state"])
            self.assertFalse(strategy["execution_enabled"])
            self.assertFalse(strategy["trading_enabled"])

        self.assertIn("ARMED_BUY", states)
        self.assertEqual("TRIGGERED_BUY", states[-1])
        self.assertEqual(1, strategy["signal_sequence"])
        self.assertEqual("BUY", strategy["last_signal"]["side"])

        heartbeat = await exchange(self.reader, self.writer, "heartbeat")
        self.assertEqual("TRIGGERED_BUY", heartbeat.payload["strategy"]["state"])
        self.assertEqual(1, heartbeat.payload["strategy"]["signal_sequence"])

    async def test_profile_apply_resets_setup_and_preserves_accumulated_bars(self):
        active = await exchange(self.reader, self.writer, "config_active_get")
        profile = fast_profile(active.payload["profile"])
        await exchange(self.reader, self.writer, "config_active_set", {"profile": profile})

        for index in range(3):
            await exchange(
                self.reader,
                self.writer,
                "bridge_snapshot",
                bridge_snapshot(index, 100 + index, 100 - index, 100 - index),
            )

        before = (await exchange(self.reader, self.writer, "heartbeat")).payload["strategy"]
        self.assertEqual("ARMED_BUY", before["state"])

        changed = copy.deepcopy(profile)
        changed["profile"]["name"] = "Task007 Changed"
        applied = await exchange(
            self.reader, self.writer, "config_active_set", {"profile": changed}
        )
        self.assertTrue(applied.payload["applied"])

        after = (await exchange(self.reader, self.writer, "heartbeat")).payload["strategy"]
        self.assertEqual("WARMUP", after["internal_state"])
        self.assertEqual("PROFILE_CHANGED", after["last_reset_reason"])
        self.assertEqual(before["bars_seen"], after["bars_seen"])
        self.assertIsNone(after["armed_side"])

    async def test_terminal_disconnect_blocks_evaluation_and_reconnect_resets_setup(self):
        active = await exchange(self.reader, self.writer, "config_active_get")
        profile = fast_profile(active.payload["profile"])
        await exchange(self.reader, self.writer, "config_active_set", {"profile": profile})

        for index in range(3):
            await exchange(
                self.reader,
                self.writer,
                "bridge_snapshot",
                bridge_snapshot(index, 100 + index, 100 - index, 100 - index),
            )

        live = (await exchange(self.reader, self.writer, "heartbeat")).payload["strategy"]
        counts = copy.deepcopy(live["bars_seen"])

        disconnected = await exchange(
            self.reader,
            self.writer,
            "bridge_snapshot",
            bridge_snapshot(3, 103, 97, 97, connected=False),
        )
        self.assertEqual("STALE", disconnected.payload["strategy"]["state"])
        self.assertEqual(counts, disconnected.payload["strategy"]["bars_seen"])

        reconnected = await exchange(
            self.reader,
            self.writer,
            "bridge_snapshot",
            bridge_snapshot(4, 104, 96, 96, connected=True),
        )
        strategy = reconnected.payload["strategy"]
        self.assertEqual("MARKET_RECONNECTED", strategy["last_reset_reason"])
        self.assertEqual(counts["M1"] + 1, strategy["bars_seen"]["M1"])
        self.assertFalse(strategy["execution_enabled"])
        self.assertFalse(strategy["trading_enabled"])


if __name__ == "__main__":
    unittest.main()
