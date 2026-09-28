from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xaupy_engine.config_schema import default_profile
from xaupy_engine.demo_once import DemoOnceController, DemoOnceError, UnavailableDemoOnceController, profile_hash
from xaupy_engine.strategy_engine import Bar, StrategyEngine, _zscore


NOW = int(datetime(2026, 9, 28, 10, tzinfo=timezone.utc).timestamp())


class DemoOnceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="xaupy-demo-once-test-")
        self.addCleanup(self.directory.cleanup)
        self.profile = default_profile()
        self.profile["stop_loss"].update(mode="FIXED", fixed_price_units=3.0)
        self.snapshot = {
            "terminal_connected": True, "account_trade_mode": "DEMO", "demo_once_capable": True,
            "demo_once_consumed": False, "account_login": 123456, "account_server": "Broker-Demo",
            "symbol": "XAUUSD", "magic": 991188, "bridge_session_id": "ea-session-1",
            "server_time": NOW - 1, "tick_time_msc": (NOW - 1) * 1000,
            "bid": 4200.0, "ask": 4200.2, "balance": 10000.0,
            "point": .01, "tick_size": .01, "tick_value": 1.0,
            "volume_min": .01, "volume_max": 100.0, "volume_step": .01, "stops_level": 10,
            "guardian": {"terminal_trade_allowed": True, "mql_trade_allowed": True,
                         "max_volume": .01, "daily_loss_limit": 200.0},
            "demo_once_guard": {"history_complete": True, "broker_day_start": NOW // 86400 * 86400,
                                "trades_today": 0, "consecutive_losses": 0, "last_exit_time": 0,
                                "day_start_balance": 10000.0, "daily_realized": 0.0,
                                "symbol_positions": 0, "symbol_orders": 0,
                                "account_trade_allowed": True, "account_expert_allowed": True},
        }
        self.strategy_status = {"available": True, "ready": True, "state": "IDLE", "signal_sequence": 10, "last_signal": None}
        self.strategy = SimpleNamespace(profile_hash=profile_hash(self.profile), history={},
                                        status_payload=lambda **kwargs: deepcopy(self.strategy_status))
        self.bridge = SimpleNamespace(latest_fresh_snapshot=lambda: deepcopy(self.snapshot))
        self.controller = DemoOnceController(self.directory.name, self.bridge, self.strategy)

    def payload(self, **changes):
        payload = {"attempt_id": str(uuid4()), "account_login": 123456, "account_server": "Broker-Demo",
                   "symbol": "XAUUSD", "magic": 991188, "profile_hash": profile_hash(self.profile),
                   "confirmed": True, "max_volume": .01, "duration_seconds": 3600}
        payload.update(changes)
        return payload

    def arm(self):
        value = self.controller.arm(self.payload(), self.profile)
        self.assertTrue(value["accepted"], value)
        return value

    def signal(self, side="BUY", **changes):
        self.snapshot.update(server_time=NOW, tick_time_msc=NOW * 1000)
        signal = {"sequence": 11, "bar_time": NOW - 60, "profile_hash": profile_hash(self.profile), "side": side}
        signal.update(changes)
        self.strategy_status.update(state=f"TRIGGERED_{side}", signal_sequence=signal["sequence"], last_signal=signal)
        return signal

    def dispatch(self, side="BUY"):
        self.arm()
        self.signal(side)
        command = self.controller.on_signal(self.profile)
        self.assertIsNotNone(command, self.controller.status())
        return command

    def result(self, command, **changes):
        value = {key: command[key] for key in (*DemoOnceController.IDENTITY, "attempt_id")}
        value.update(order_send_called=True, retcode=10009, retcode_external=0, order_ticket=1001,
                     deal_ticket=1002, filled_volume=command["volume"], fill_price=command["reference_price"],
                     sl=command["sl"], tp=command["tp"], status="FILLED", reason="broker deal evidence")
        value.update(changes)
        return value

    def test_profile_hash_is_strategy_exact_hash(self):
        self.assertEqual(StrategyEngine(self.profile).profile_hash, profile_hash(self.profile))

    def test_new_closed_bar_signal_dispatches_exact_bounded_command_once(self):
        command = self.dispatch()
        self.assertEqual({"kind", "attempt_id", "account_login", "account_server", "symbol", "magic", "profile_hash",
                          "bridge_session_id", "side", "volume", "reference_price", "sl", "tp",
                          "max_deviation_points", "max_spread_price_units", "max_loss_money", "issued_server_time",
                          "expires_server_time", "signal_sequence", "signal_bar_time"}, set(command))
        self.assertTrue(all(type(v) in (str, int, float, bool) for v in command.values()))
        self.assertEqual(.01, command["volume"])
        self.assertEqual(5, command["expires_server_time"] - command["issued_server_time"])
        self.assertLess(command["sl"], self.snapshot["bid"])
        self.assertGreater(command["tp"], self.snapshot["ask"])
        ledger = json.loads(self.controller.path.read_text())
        self.assertEqual("DISPATCHED", ledger["state"])
        self.assertTrue(ledger["budget_consumed"])
        self.assertEqual(command, ledger["command"])
        self.assertIsNone(self.controller.on_signal(self.profile))
        self.assertFalse(self.controller.arm(self.payload(), self.profile)["accepted"])
        self.assertFalse(self.controller.status()["execution_enabled"])

    def test_sell_has_protective_stops_and_volume(self):
        command = self.dispatch("SELL")
        self.assertGreater(command["sl"], self.snapshot["ask"])
        self.assertLess(command["tp"], self.snapshot["bid"])

    def test_intrabar_timestamp_must_be_after_arm_not_candle_open(self):
        self.arm()
        self.signal(bar_time=NOW - 60, tick_time_msc=NOW * 1000)
        self.assertIsNotNone(self.controller.on_signal(self.profile))

    def test_arm_requires_explicit_exact_identity_and_bounded_limits(self):
        for changes, code in [({"confirmed": False}, "CONFIRMATION_REQUIRED"),
                              ({"attempt_id": "not-a-uuid"}, "INVALID_ATTEMPT_ID"),
                              ({"profile_hash": "f" * 64}, "PROFILE_HASH_MISMATCH"),
                              ({"account_login": 2222}, "ACCOUNT_OR_SYMBOL_MISMATCH"),
                              ({"account_server": "Broker-Real"}, "ACCOUNT_OR_SYMBOL_MISMATCH"),
                              ({"symbol": "EURUSD"}, "ACCOUNT_OR_SYMBOL_MISMATCH"),
                              ({"magic": 42}, "ACCOUNT_OR_SYMBOL_MISMATCH"),
                              ({"max_volume": .02}, "VOLUME_LIMIT_001"),
                              ({"max_volume": True}, "INVALID_MAX_VOLUME"),
                              ({"max_volume": float("nan")}, "INVALID_MAX_VOLUME"),
                              ({"duration_seconds": 86401}, "DURATION_LIMIT"),
                              ({"duration_seconds": True}, "INVALID_DURATION_SECONDS")]:
            with self.subTest(changes=changes):
                value = self.controller.arm(self.payload(**changes), self.profile)
                self.assertFalse(value["accepted"])
                self.assertEqual(code, value["code"])
        self.assertEqual("DISABLED", self.controller.status()["state"])

    def test_real_or_unknown_account_and_missing_capability_never_arm(self):
        for key, bad in [("account_trade_mode", "REAL"), ("account_trade_mode", "UNKNOWN"),
                         ("terminal_connected", False), ("demo_once_capable", False),
                         ("demo_once_consumed", True), ("demo_once_consumed", None),
                         ("tick_time_msc", (NOW - 10) * 1000), ("guardian", None)]:
            with self.subTest(key=key, value=bad):
                original = self.snapshot[key]
                self.snapshot[key] = bad
                self.assertFalse(self.controller.arm(self.payload(), self.profile)["accepted"])
                self.snapshot[key] = original

    def test_risk_history_exposure_and_permissions_fail_closed(self):
        changes = {"history_complete": False, "broker_day_start": NOW // 86400 * 86400 - 86400,
                   "trades_today": 8, "consecutive_losses": 3, "last_exit_time": NOW - 60,
                   "day_start_balance": 0, "daily_realized": -200.0, "symbol_positions": 1,
                   "symbol_orders": 1, "account_trade_allowed": False, "account_expert_allowed": False}
        for key, value in changes.items():
            with self.subTest(key=key):
                original = self.snapshot["demo_once_guard"][key]
                self.snapshot["demo_once_guard"][key] = value
                self.assertFalse(self.controller.arm(self.payload(), self.profile)["accepted"])
                self.snapshot["demo_once_guard"][key] = original
        for key in ("terminal_trade_allowed", "mql_trade_allowed"):
            self.snapshot["guardian"][key] = False
            self.assertFalse(self.controller.arm(self.payload(), self.profile)["accepted"])
            self.snapshot["guardian"][key] = True

    def test_unsupported_entry_news_and_timezone_rejected(self):
        for section, key, value in [("entry", "mode", "STOP_CONFIRM"), ("take_profit", "mode", "ZRSI_DYNAMIC"),
                                    ("news", "enabled", True), ("sessions", "timezone", "Asia/Saigon")]:
            with self.subTest(section=section):
                profile = deepcopy(self.profile)
                profile[section][key] = value
                self.assertFalse(self.controller.arm(self.payload(), profile)["accepted"])

    def test_same_arm_is_idempotent_and_never_extends_deadline(self):
        payload = self.payload()
        first = self.controller.arm(payload, self.profile)
        second = self.controller.arm({**payload, "duration_seconds": 86400}, self.profile)
        self.assertEqual("ALREADY_ARMED", second["code"])
        self.assertEqual(first["armed_until_utc_ms"], second["armed_until_utc_ms"])
        self.assertFalse(self.controller.arm(self.payload(), self.profile)["accepted"])

    def test_restart_suspends_unconsumed_arm_and_requires_explicit_rearm(self):
        self.arm()
        restarted = DemoOnceController(self.directory.name, self.bridge, self.strategy)
        self.assertEqual("SUSPENDED", restarted.status()["state"])
        self.signal()
        self.assertIsNone(restarted.on_signal(self.profile))
        self.assertTrue(restarted.arm(self.payload(), self.profile)["accepted"])
        self.assertIsNone(restarted.on_signal(self.profile))  # Existing signal now baseline.

    def test_restart_of_dispatched_command_is_unknown_and_never_releases_again(self):
        command = self.dispatch()
        restarted = DemoOnceController(self.directory.name, self.bridge, self.strategy)
        self.assertEqual("UNKNOWN", restarted.status()["state"])
        self.assertIsNone(restarted.on_signal(self.profile))
        self.assertFalse(restarted.arm(self.payload(), self.profile)["accepted"])
        self.assertEqual("FILLED", restarted.record_result(self.result(command))["state"])

    def test_cancel_and_lazy_expiration_do_not_dispatch(self):
        self.assertFalse(self.controller.cancel({})["accepted"])
        self.assertEqual("DISABLED", self.controller.status()["state"])
        self.assertFalse(self.controller.path.exists())
        armed = self.arm()
        self.assertFalse(self.controller.cancel({"attempt_id": str(uuid4())})["accepted"])
        self.assertTrue(self.controller.cancel({"attempt_id": armed["attempt_id"]})["accepted"])
        self.signal()
        self.assertIsNone(self.controller.on_signal(self.profile))
        armed = self.arm()
        with patch("xaupy_engine.demo_once.time.time", return_value=armed["armed_until_utc_ms"] / 1000 + 1):
            self.assertEqual("EXPIRED", self.controller.status()["state"])
            self.assertIsNone(self.controller.on_signal(self.profile))

    def test_no_old_or_stale_signal_can_be_revived_after_guards_clear(self):
        self.arm()
        self.signal()
        self.snapshot["ask"] = self.snapshot["bid"] + 1.0
        self.assertIsNone(self.controller.on_signal(self.profile))
        self.assertEqual("SPREAD_LIMIT", self.controller.status()["last_blocker"])
        self.snapshot["ask"] = self.snapshot["bid"] + .2
        self.assertIsNone(self.controller.on_signal(self.profile))
        self.signal(sequence=12, tick_time_msc=NOW * 1000 + 1)
        self.assertIsNotNone(self.controller.on_signal(self.profile))

    def test_permission_blocked_signal_is_not_revived_when_permission_returns(self):
        self.arm()
        self.signal()
        self.snapshot["guardian"]["terminal_trade_allowed"] = False
        self.assertIsNone(self.controller.on_signal(self.profile))
        self.snapshot["guardian"]["terminal_trade_allowed"] = True
        self.assertIsNone(self.controller.on_signal(self.profile))
        self.signal(sequence=12)
        self.assertIsNotNone(self.controller.on_signal(self.profile))

    def test_signal_integrity_and_freshness_are_required(self):
        for change in [{"sequence": 10}, {"bar_time": NOW - 120}, {"tick_time_msc": (NOW - 1) * 1000},
                       {"tick_time_msc": (NOW + 3) * 1000}, {"profile_hash": "bad"}]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                self.controller = DemoOnceController(directory, self.bridge, self.strategy)
                self.snapshot.update(server_time=NOW - 1, tick_time_msc=(NOW - 1) * 1000)
                self.strategy_status.update(state="IDLE", signal_sequence=10, last_signal=None)
                self.arm()
                self.signal(**change)
                self.assertIsNone(self.controller.on_signal(self.profile))
                self.assertFalse(self.controller.status()["budget_consumed"])

    def test_profile_and_bridge_session_changes_suspend_authorization(self):
        self.arm()
        self.profile["profile"]["name"] = "Changed"
        self.assertIsNone(self.controller.on_signal(self.profile))
        self.assertEqual("PROFILE_CHANGED", self.controller.status()["reason"])
        self.strategy.profile_hash = profile_hash(self.profile)
        self.arm()
        self.snapshot["bridge_session_id"] = "different-session"
        self.assertIsNone(self.controller.on_signal(self.profile))
        self.assertEqual("BRIDGE_IDENTITY_CHANGED", self.controller.status()["reason"])

    def test_session_guard_is_checked_at_signal(self):
        self.profile["sessions"].update(session1_start="11:00", session1_end="12:00", session2_enabled=False)
        self.strategy.profile_hash = profile_hash(self.profile)
        self.arm()
        self.signal()
        self.assertIsNone(self.controller.on_signal(self.profile))
        self.assertEqual("SESSION_TIME_BLOCKED", self.controller.status()["last_blocker"])

    def test_broker_volume_minimum_and_step_are_not_rounded_up(self):
        self.snapshot["volume_min"] = .1
        self.assertFalse(self.controller.arm(self.payload(), self.profile)["accepted"])
        self.snapshot["volume_min"] = .001
        self.snapshot["volume_step"] = .003
        command = self.dispatch()
        self.assertAlmostEqual(.009, command["volume"])

    def test_stops_checked_against_close_quote_and_broker_distance(self):
        self.arm()
        self.signal()
        self.snapshot["stops_level"] = 290  # SL distance from entry 3.0, but from Bid only 2.8.
        self.assertIsNone(self.controller.on_signal(self.profile))
        self.assertEqual("INVALID_SERVER_STOPS", self.controller.status()["last_blocker"])

    def test_worst_slippage_and_fees_count_toward_risk_and_daily_remainder(self):
        self.arm()
        self.signal()
        self.snapshot["demo_once_guard"]["daily_realized"] = -197.0
        self.assertIsNone(self.controller.on_signal(self.profile))
        self.assertEqual("RISK_BUDGET_EXCEEDED", self.controller.status()["last_blocker"])

    def test_min_net_rr_uses_worst_admissible_entry(self):
        self.profile["stop_loss"]["fixed_price_units"] = 5.0
        self.strategy.profile_hash = profile_hash(self.profile)
        self.arm()
        self.signal()
        self.assertIsNone(self.controller.on_signal(self.profile))
        self.assertEqual("MIN_NET_RR", self.controller.status()["last_blocker"])

    def test_structure_stop_uses_only_closed_fresh_bars(self):
        self.profile["stop_loss"]["mode"] = "STRUCTURE"
        self.strategy.profile_hash = profile_hash(self.profile)
        self.strategy.history["M5"] = [Bar(NOW - n * 300, 4200, 4201, 4198, 4200) for n in (3, 2, 1)]
        self.strategy.history["M5"].append(Bar(NOW, 4200, 5000, 4000, 4200))
        command = self.dispatch()
        self.assertAlmostEqual(4197.7, command["sl"])

    def test_structure_stop_rejects_stale_history(self):
        self.profile["stop_loss"]["mode"] = "STRUCTURE"
        self.strategy.profile_hash = profile_hash(self.profile)
        self.strategy.history["M5"] = [Bar(NOW - n * 300, 4200, 4201, 4198, 4200) for n in (4, 3, 2)]
        self.arm()
        self.signal()
        self.assertIsNone(self.controller.on_signal(self.profile))
        self.assertEqual("STOP_HISTORY_STALE", self.controller.status()["last_blocker"])

    def test_no_command_escapes_failed_durable_consumption(self):
        self.arm()
        self.signal()
        from xaupy_engine.settings import _atomic_json
        calls = []
        def fail_dispatch(path, value):
            calls.append(value["state"])
            if value["state"] == "DISPATCHED":
                raise OSError("simulated disk failure")
            _atomic_json(path, value)
        with patch("xaupy_engine.demo_once._atomic_json", side_effect=fail_dispatch):
            self.assertIsNone(self.controller.on_signal(self.profile))
        self.assertEqual(["ARMED", "DISPATCHED"], calls)
        self.assertEqual("UNKNOWN", self.controller.status()["state"])
        self.assertTrue(self.controller.status()["budget_consumed"])
        self.assertFalse(self.controller.arm(self.payload(), self.profile)["accepted"])

    def test_corrupt_state_and_stale_lock_fail_closed(self):
        self.controller.path.write_text('{"schema_version":1,"state":"ARMED","budget_consumed":false}')
        restarted = DemoOnceController(self.directory.name, self.bridge, self.strategy)
        self.assertTrue(restarted.status()["budget_consumed"])
        self.assertFalse(restarted.arm(self.payload(), self.profile)["accepted"])
        self.controller.lock_path.write_text("crashed process")
        with self.assertRaises(DemoOnceError):
            DemoOnceController(self.directory.name, self.bridge, self.strategy)

    def test_unavailable_fallback_rejects_all_mutations_without_touching_ledger(self):
        self.controller.lock_path.write_text("crashed process")
        original = self.controller.lock_path.read_bytes()
        fallback = UnavailableDemoOnceController("CONTROLLER_STATE_LOCKED")
        for value in [fallback.arm(self.payload(), self.profile), fallback.cancel({}), fallback.record_result({})]:
            self.assertFalse(value["accepted"])
            self.assertEqual("UNKNOWN", value["state"])
            self.assertTrue(value["budget_consumed"])
            self.assertEqual("CONTROLLER_STATE_LOCKED", value["reason"])
        self.assertIsNone(fallback.on_signal(self.profile))
        self.assertFalse(fallback.status()["execution_enabled"])
        self.assertEqual(original, self.controller.lock_path.read_bytes())
        self.assertFalse(self.controller.path.exists())

    def test_malformed_persisted_shapes_do_not_crash_heartbeat_or_unlock_arm(self):
        self.arm()
        valid = json.loads(self.controller.path.read_text())
        malformed = [
            {"schema_version": 1, "state": "ARMED", "budget_consumed": False},
            {**valid, "authorization": []},
            {**valid, "armed_until_utc_ms": "tomorrow"},
            {**valid, "armed_until_utc_ms": None},
            {**valid, "armed_until_utc_ms": True},
            {**valid, "armed_until_utc_ms": 0},
            {**valid, "armed_until_utc_ms": float("nan")},
            {**valid, "armed_until_utc_ms": valid["armed_at_utc_ms"] + 86400001},
            {**valid, "state": "DISPATCHED", "budget_consumed": True, "command": None},
            {**valid, "state": "DISPATCHED", "budget_consumed": True, "dispatched_at_utc_ms": "bad"},
            {"schema_version": 1, "state": "FILLED", "budget_consumed": True, "result": []},
            {"schema_version": 1, "state": "UNKNOWN", "budget_consumed": True, "result": None},
        ]
        for index, ledger in enumerate(malformed):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "demo-once-v1.json"
                path.write_text(json.dumps(ledger), encoding="utf-8")
                original = path.read_bytes()
                broken = DemoOnceController(directory, self.bridge, self.strategy)
                for _ in range(2):
                    status = broken.status()
                    self.assertEqual("UNKNOWN", status["state"])
                    self.assertTrue(status["budget_consumed"])
                    self.assertFalse(broken.arm(self.payload(), self.profile)["accepted"])
                    self.assertFalse(broken.cancel({"attempt_id": ledger.get("attempt_id")})["accepted"])
                    self.assertFalse(broken.record_result({})["accepted"])
                    self.assertIsNone(broken.on_signal(self.profile))
                self.assertEqual(original, path.read_bytes())

    def test_corruption_after_arm_is_latched_closed_for_current_process(self):
        self.arm()
        self.controller.path.write_text('{"schema_version":1,"state":"ARMED","budget_consumed":false,"armed_until_utc_ms":"bad"}')
        corrupt = self.controller.path.read_bytes()
        self.assertEqual("UNKNOWN", self.controller.status()["state"])
        self.assertFalse(self.controller.arm(self.payload(), self.profile)["accepted"])
        self.assertEqual(corrupt, self.controller.path.read_bytes())

    def test_broker_deal_evidence_is_required_not_send_ack_or_ticket(self):
        command = self.dispatch()
        for changes in [{"deal_ticket": 0}, {"retcode": 10004}, {"order_send_called": False},
                        {"filled_volume": 0}, {"sl": 0}, {"sl": command["reference_price"] + 1}]:
            with self.subTest(changes=changes):
                value = self.controller.record_result(self.result(command, **changes))
                self.assertNotEqual("FILLED", value["state"])
                self.assertTrue(value["budget_consumed"])
                self.assertFalse(self.controller.arm(self.payload(), self.profile)["accepted"])
        value = self.controller.record_result(self.result(command))
        self.assertEqual("FILLED", value["state"])
        self.assertEqual(1002, value["deal_ticket"])
        self.assertEqual(.01, value["volume"])
        self.assertEqual("BUY", value["side"])
        self.assertEqual("ALREADY_FILLED", self.controller.record_result(self.result(command))["code"])

    def test_partial_fill_consumes_entire_budget_and_bad_identity_is_rejected(self):
        command = self.dispatch()
        self.assertFalse(self.controller.record_result(self.result(command, account_login=42))["accepted"])
        self.assertFalse(self.controller.record_result(self.result(command, filled_volume=.02))["accepted"])
        value = self.controller.record_result(self.result(command, retcode=10010, filled_volume=.005))
        self.assertEqual("FILLED", value["state"])
        self.assertEqual(.005, value["filled_volume"])
        self.assertEqual(.005, value["volume"])
        self.assertEqual(.01, value["authorized_volume"])
        self.assertFalse(self.controller.cancel({"attempt_id": command["attempt_id"]})["accepted"])

    def test_lost_result_becomes_unknown_but_verified_late_deal_can_complete(self):
        command = self.dispatch()
        dispatched = self.controller.status()["dispatched_at_utc_ms"]
        with patch("xaupy_engine.demo_once.time.time", return_value=dispatched / 1000 + 31):
            value = self.controller.status()
        self.assertEqual("UNKNOWN", value["state"])
        self.assertTrue(value["budget_consumed"])
        self.assertIsNone(self.controller.on_signal(self.profile))
        value = self.controller.record_result(self.result(command, retcode=10008))
        self.assertEqual("FILLED", value["state"])
        saved_result = value["result"]
        value = self.controller.record_result(self.result(command, deal_ticket=9999))
        self.assertEqual("ALREADY_FILLED", value["code"])
        self.assertEqual(saved_result, value["result"])

    def test_positive_but_unapproved_stops_do_not_claim_verified_acceptance(self):
        command = self.dispatch()
        value = self.controller.record_result(self.result(command, sl=command["sl"] - 1))
        self.assertEqual("UNKNOWN", value["state"])
        self.assertTrue(value["budget_consumed"])
        value = self.controller.record_result(self.result(command, tp=command["tp"] + 1))
        self.assertEqual("UNKNOWN", value["state"])

    def test_crash_claim_with_false_called_flag_remains_unknown(self):
        command = self.dispatch()
        value = self.controller.record_result(self.result(command, status="UNKNOWN", order_send_called=False,
                                             retcode=0, order_ticket=0, deal_ticket=0, filled_volume=0,
                                             reason="DURABLE_CLAIM_SEND_OUTCOME_NOT_RECORDED"))
        self.assertEqual("UNKNOWN", value["state"])
        self.assertTrue(value["budget_consumed"])
        self.assertFalse(self.controller.arm(self.payload(), self.profile)["accepted"])

    def test_real_strategy_threshold_latch_waits_next_bar_before_dispatch(self):
        self.profile["timeframes"] = {role: "M1" for role in ("direction", "pullback", "trigger")}
        self.profile["direction"]["ma_enabled"] = False
        self.profile["pullback"].update(rsi_enabled=False, z_enabled=True, z_sell_level=2.5)
        self.profile["trigger"].update(rsi_enabled=False, z_enabled=True, z_reversal_delta=.3, confirm_closed_bar=False)
        engine = StrategyEngine(self.profile)
        closes = [99.0, 101.0] * 20
        engine.history["M1"] = [Bar(NOW - (40 - i) * 60, value, value, value, value) for i, value in enumerate(closes)]
        def tick(sequence, offset, bid):
            self.snapshot.update(server_time=NOW + offset // 1000, tick_time_msc=NOW * 1000 + offset, bid=bid, ask=bid + .2)
            return engine.ingest_tick_batch({"symbol": "XAUUSD", "server_time": self.snapshot["server_time"],
                "tick_batch": {"stream_id": "isolated-real-strategy", "sequence": sequence, "complete": sequence > 1,
                               "ticks": [{"time_msc": self.snapshot["tick_time_msc"], "bid": bid, "ask": bid + .2}]}})
        def price(z):
            lows, highs = .001, 1000.0
            for _ in range(80):
                mid = (lows + highs) / 2
                if _zscore([b.close for b in engine.history["M1"]] + [mid], 20) < z:
                    lows = mid
                else:
                    highs = mid
            return (lows + highs) / 2
        tick(1, 500, 100)
        tick(2, 1000, 100)
        self.strategy = engine
        self.controller = DemoOnceController(self.directory.name, self.bridge, engine)
        self.arm()
        tick(3, 10000, price(2.5001))
        tick(4, 50000, price(2.2))
        self.assertEqual("ARMED_SELL", engine.state)
        self.assertIsNone(self.controller.on_signal(self.profile))
        engine.ingest_snapshot({"symbol": "XAUUSD", "bars": {"M1": {"time": NOW, "open": 100,
            "high": 110, "low": 90, "close": self.snapshot["bid"], "tick_volume": 100}}})
        tick(5, 61000, price(2.2))
        self.assertEqual("TRIGGERED_SELL", engine.state)
        command = self.controller.on_signal(self.profile)
        self.assertIsNotNone(command, self.controller.status())
        self.assertEqual("SELL", command["side"])
        self.assertEqual(NOW + 60, command["signal_bar_time"])
        self.assertIsNone(self.controller.on_signal(self.profile))


if __name__ == "__main__":
    unittest.main()
