import asyncio
from copy import deepcopy
import pathlib
import sys
import time
import unittest
from uuid import uuid4

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.bridge_state import BridgeRegistry, BridgeSnapshotError
from xaupy_engine.config_schema import default_profile
from xaupy_engine.contracts import Envelope
from xaupy_engine.execution_simulator import ManualActionSimulator
from xaupy_engine.server import EngineServer


def _bar():
    return {
        "time": 1790240000,
        "open": 4280.0,
        "high": 4282.0,
        "low": 4279.0,
        "close": 4281.0,
        "tick_volume": 123,
    }


def bridge_snapshot(*, positions=True, orders=True, trade_mode="DEMO"):
    position_rows = [
        {
            "ticket": 32874561,
            "magic": 991188,
            "symbol": "XAUUSD",
            "side": "BUY",
            "volume": 0.10,
            "price_open": 4280.0,
            "price_current": 4282.0,
            "sl": 4275.0,
            "tp": 4290.0,
            "profit": 20.0,
            "swap": -1.0,
            "time": 1790240000,
            "comment": "XAUPY",
        }
    ] if positions else []

    order_rows = [
        {
            "ticket": 32874570,
            "magic": 991188,
            "symbol": "XAUUSD",
            "type": "BUY STOP",
            "volume_initial": 0.10,
            "volume_current": 0.10,
            "price_open": 4285.0,
            "price_current": 4282.0,
            "sl": 4281.0,
            "tp": 4295.0,
            "state": "PLACED",
            "time_setup": 1790240100,
            "comment": "XAUPY",
        }
    ] if orders else []

    deals = [
        {
            "ticket": 32874560,
            "order_ticket": 32874559,
            "magic": 991188,
            "symbol": "XAUUSD",
            "side": "SELL",
            "entry": "OUT",
            "volume": 0.10,
            "price_in": 4278.00,
            "price_out": 4282.10,
            "profit": 44.0,
            "commission": -0.5,
            "swap": 0.0,
            "realized_total": 43.5,
            "reason": "TP",
            "time": 1790240200,
            "comment": "XAUPY",
        }
    ]

    return {
        "bridge_version": "0.9.0-task009",
        "symbol": "XAUUSD",
        "magic": 991188,
        "terminal_connected": True,
        "account_trade_mode": trade_mode,
        "account_login": 12345678,
        "account_currency": "USD",
        "leverage": 100,
        "balance": 10000.0,
        "equity": 10000.0,
        "margin_free": 9950.0,
        "bid": 4282.00,
        "ask": 4282.30,
        "spread_points": 30.0,
        "digits": 2,
        "point": 0.01,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "stops_level": 10,
        "freeze_level": 5,
        "positions_count": len(position_rows),
        "orders_count": len(order_rows),
        "own_daily_realized": 43.5,
        "positions": position_rows,
        "orders": order_rows,
        "deals": deals,
        "guardian": {
            "execution_locked": True,
            "execution_ready": False,
            "reason": "TASK003_EXECUTION_LOCKED",
            "daily_realized": 43.5,
            "daily_loss_limit": 200.0,
        },
        "bars": {tf: _bar() for tf in ("M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4")},
    }


def profile_for_simulation():
    profile = default_profile()
    profile["risk"]["max_open_positions"] = 3
    profile["management"]["trailing_enabled"] = True
    return profile


class OrdersProjectionTests(unittest.TestCase):
    def test_real_ticket_projection_and_kpis(self):
        registry = BridgeRegistry()
        registry.record_snapshot(bridge_snapshot())
        book = registry.orders_positions_payload()

        self.assertTrue(book["available"])
        self.assertEqual(1, book["positions_count"])
        self.assertEqual(1, book["orders_count"])
        self.assertEqual(19.0, book["open_pl"])
        self.assertEqual(43.5, book["realized_pl"])
        self.assertAlmostEqual(0.10, book["exposure_lots"])
        self.assertTrue(book["risk_complete"])
        self.assertAlmostEqual(50.0, book["risk_usd"])
        self.assertAlmostEqual(0.5, book["risk_pct"])
        self.assertEqual(32874561, book["positions"][0]["ticket"])
        self.assertEqual(32874570, book["orders"][0]["ticket"])
        self.assertEqual(32874560, book["deals"][0]["ticket"])
        self.assertTrue(book["broker_execution_locked"])
        self.assertTrue(book["simulation_only"])

    def test_stale_book_clears_ticket_rows(self):
        registry = BridgeRegistry(stale_seconds=0.01)
        registry.record_snapshot(bridge_snapshot())
        time.sleep(0.03)
        book = registry.orders_positions_payload()

        self.assertFalse(book["available"])
        self.assertEqual([], book["positions"])
        self.assertEqual([], book["orders"])
        self.assertEqual([], book["deals"])

    def test_count_mismatch_is_rejected(self):
        payload = bridge_snapshot()
        payload["positions_count"] = 99
        with self.assertRaises(BridgeSnapshotError):
            BridgeRegistry().record_snapshot(payload)

    def test_wrong_magic_inside_owned_collection_is_rejected(self):
        payload = bridge_snapshot()
        payload["positions"][0]["magic"] = 123
        with self.assertRaises(BridgeSnapshotError):
            BridgeRegistry().record_snapshot(payload)


class ManualActionSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.registry = BridgeRegistry()
        self.profile = profile_for_simulation()
        self.simulator = ManualActionSimulator(self.registry)

    def simulate(self, action, **values):
        payload = {
            "intent_id": str(uuid4()),
            "action": action,
            "confirmed": True,
            **values,
        }
        return self.simulator.simulate(payload, self.profile)

    def test_market_preview_is_accepted_but_never_mutates_broker(self):
        self.registry.record_snapshot(bridge_snapshot(positions=False, orders=False))
        result = self.simulate(
            "MARKET_BUY",
            volume=0.10,
            sl_points=50,
            tp_points=100,
        )

        self.assertTrue(result["accepted"])
        self.assertEqual("SIMULATED_ACCEPTED", result["code"])
        self.assertTrue(result["simulated"])
        self.assertFalse(result["broker_mutated"])
        self.assertFalse(result["trading_enabled"])
        self.assertFalse(result["execution_enabled"])
        self.assertEqual(4282.30, result["preview"]["simulated_fill_price"])
        self.assertAlmostEqual(4281.80, result["preview"]["server_sl"])
        self.assertAlmostEqual(4283.30, result["preview"]["take_profit"])
        self.assertFalse(result["preview"]["broker_request_sent"])

    def test_server_sl_is_required(self):
        self.registry.record_snapshot(bridge_snapshot(positions=False, orders=False))
        result = self.simulate("MARKET_SELL", volume=0.10, tp_points=100)
        self.assertFalse(result["accepted"])
        self.assertEqual("SERVER_SL_REQUIRED", result["code"])

    def test_volume_step_and_max_lot_are_guarded(self):
        self.registry.record_snapshot(bridge_snapshot(positions=False, orders=False))
        bad_step = self.simulate("MARKET_BUY", volume=0.015, sl_points=50)
        too_large = self.simulate("MARKET_BUY", volume=0.11, sl_points=50)

        self.assertEqual("VOLUME_STEP_INVALID", bad_step["code"])
        self.assertEqual("VOLUME_ABOVE_MAX", too_large["code"])

    def test_real_account_is_blocked_even_for_simulation_control(self):
        self.registry.record_snapshot(bridge_snapshot(positions=False, trade_mode="REAL"))
        result = self.simulate("MARKET_BUY", volume=0.10, sl_points=50)
        self.assertFalse(result["accepted"])
        self.assertEqual("DEMO_ONLY", result["code"])

    def test_confirmation_is_required(self):
        self.registry.record_snapshot(bridge_snapshot())
        result = self.simulator.simulate(
            {
                "intent_id": str(uuid4()),
                "action": "CLOSE_POSITION",
                "confirmed": False,
                "ticket": 32874561,
            },
            self.profile,
        )
        self.assertEqual("CONFIRMATION_REQUIRED", result["code"])

    def test_unowned_ticket_is_rejected(self):
        self.registry.record_snapshot(bridge_snapshot())
        result = self.simulate("CLOSE_POSITION", ticket=999999)
        self.assertFalse(result["accepted"])
        self.assertEqual("POSITION_NOT_FOUND", result["code"])

    def test_break_even_cannot_widen_sl(self):
        payload = bridge_snapshot()
        payload["positions"][0]["sl"] = 4281.0
        self.registry.record_snapshot(payload)
        result = self.simulate("MOVE_SL_BE", ticket=32874561)
        self.assertFalse(result["accepted"])
        self.assertEqual("NEVER_WIDEN_SL", result["code"])

    def test_partial_close_preview_respects_volume(self):
        payload = bridge_snapshot()
        payload["positions"][0]["volume"] = 0.10
        self.registry.record_snapshot(payload)
        result = self.simulate("PARTIAL_CLOSE", ticket=32874561, percent=50)
        self.assertTrue(result["accepted"])
        self.assertAlmostEqual(0.05, result["preview"]["close_volume"])
        self.assertAlmostEqual(0.05, result["preview"]["remaining_volume"])

    def test_pending_modify_and_cancel_require_owned_order(self):
        self.registry.record_snapshot(bridge_snapshot())
        modify = self.simulate("MODIFY_PENDING", ticket=32874570, price=4286.0)
        cancel = self.simulate("CANCEL_PENDING", ticket=32874570)

        self.assertTrue(modify["accepted"])
        self.assertTrue(cancel["accepted"])
        self.assertEqual(4286.0, modify["preview"]["changes"]["price"])

    def test_intent_is_idempotent_and_conflicts_are_rejected(self):
        self.registry.record_snapshot(bridge_snapshot())
        intent_id = str(uuid4())
        request = {
            "intent_id": intent_id,
            "action": "CLOSE_POSITION",
            "confirmed": True,
            "ticket": 32874561,
        }
        first = self.simulator.simulate(request, self.profile)
        replay = self.simulator.simulate(deepcopy(request), self.profile)
        conflict = self.simulator.simulate(
            {
                **request,
                "ticket": 999999,
            },
            self.profile,
        )

        self.assertEqual(first, replay)
        self.assertEqual("INTENT_ID_CONFLICT", conflict["code"])

    def test_stale_snapshot_blocks_action(self):
        registry = BridgeRegistry(stale_seconds=0.01)
        registry.record_snapshot(bridge_snapshot())
        simulator = ManualActionSimulator(registry)
        time.sleep(0.03)
        result = simulator.simulate(
            {
                "intent_id": str(uuid4()),
                "action": "CLOSE_ALL",
                "confirmed": True,
            },
            self.profile,
        )
        self.assertEqual("STALE_MARKET_DATA", result["code"])


async def exchange(reader, writer, message_type, payload=None):
    request = Envelope.create(message_type, payload or {})
    writer.write((request.to_json() + "\n").encode("utf-8"))
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=2)
    response = Envelope.from_json(line.decode("utf-8").rstrip("\r\n"))
    if response.request_id != request.request_id:
        raise AssertionError("response request_id mismatch")
    return response


class Task009ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = EngineServer(port=0)
        self.server.active_profile = profile_for_simulation()
        self.server.strategy.set_profile(self.server.active_profile)
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.close()

    async def connect(self):
        return await asyncio.open_connection("127.0.0.1", self.server.bound_port)

    async def test_heartbeat_projects_order_book(self):
        reader, writer = await self.connect()
        await exchange(reader, writer, "bridge_snapshot", bridge_snapshot())
        heartbeat = await exchange(reader, writer, "heartbeat")
        book = heartbeat.payload["orders_positions"]

        self.assertTrue(book["available"])
        self.assertEqual(32874561, book["positions"][0]["ticket"])
        self.assertFalse(heartbeat.payload["execution_enabled"])
        self.assertFalse(heartbeat.payload["trading_enabled"])

        writer.close()
        await writer.wait_closed()

    async def test_manual_action_simulate_ack_is_never_execution(self):
        reader, writer = await self.connect()
        await exchange(reader, writer, "bridge_snapshot", bridge_snapshot(positions=False))
        response = await exchange(
            reader,
            writer,
            "manual_action_simulate",
            {
                "intent_id": str(uuid4()),
                "action": "MARKET_BUY",
                "confirmed": True,
                "volume": 0.10,
                "sl_points": 50,
                "tp_points": 100,
            },
        )

        self.assertEqual("manual_action_simulate_ack", response.type)
        self.assertTrue(response.payload["accepted"])
        self.assertTrue(response.payload["simulated"])
        self.assertFalse(response.payload["broker_mutated"])
        self.assertFalse(response.payload["execution_enabled"])
        self.assertFalse(response.payload["trading_enabled"])

        writer.close()
        await writer.wait_closed()

    async def test_trade_intent_is_still_unsupported(self):
        reader, writer = await self.connect()
        response = await exchange(
            reader,
            writer,
            "trade_intent",
            {"symbol": "XAUUSD", "side": "BUY", "volume": 0.1},
        )
        self.assertEqual("error", response.type)
        self.assertEqual("UNSUPPORTED_MESSAGE", response.payload["code"])
        self.assertFalse(response.payload["execution_enabled"])

        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    unittest.main()
