from __future__ import annotations

import copy
import math
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from xaupy_engine.backtest import BacktestEngine, BacktestError
from xaupy_engine.config_schema import default_profile
from xaupy_engine.strategy_engine import Bar, StrategyDataError, StrategyEngine, _rsi, _zscore

START = 1_800_000_000


def profile(side="SELL", indicator="z"):
    result = default_profile()
    result["strategy"].update(allow_buy=side == "BUY", allow_sell=side == "SELL")
    result["timeframes"] = {role: "M1" for role in ("direction", "pullback", "trigger")}
    result["direction"]["ma_enabled"] = False
    result["pullback"].update(rsi_enabled=indicator == "rsi", z_enabled=indicator == "z",
                              z_period=20, z_sell_level=2.5, z_buy_level=-2.5,
                              rsi_period=14, rsi_sell_level=70, rsi_buy_level=30)
    result["trigger"].update(confirm_closed_bar=False, rsi_enabled=indicator == "rsi",
                             z_enabled=indicator == "z", z_period=20, rsi_period=14,
                             z_reversal_delta=0.3, rsi_reversal_delta=3.0)
    return result


def engine_for(side="SELL", indicator="z"):
    engine = StrategyEngine(profile(side, indicator))
    closes = [99.0, 101.0] * 20
    engine.history["M1"] = [Bar(START - (len(closes) - i) * 60, value, value, value, value)
                            for i, value in enumerate(closes)]
    return engine


def price_for(engine, value, indicator="z"):
    closes = [bar.close for bar in engine.history["M1"]]
    calculate, period = (_zscore, 20) if indicator == "z" else (_rsi, 14)
    low, high = 0.001, 1000.0
    for _ in range(90):
        mid = (low + high) / 2
        if calculate(closes + [mid], period) < value:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def batch(sequence, rows, *, stream="test-observed-ticks", complete=True):
    return {"symbol": "XAUUSD", "server_time": START + 600,
            "tick_batch": {"stream_id": stream, "sequence": sequence, "complete": complete,
                           "ticks": [{"time_msc": START * 1000 + milliseconds, "bid": bid, "ask": bid + 0.2}
                                     for milliseconds, bid in rows]}}


def baseline(engine):
    return engine.ingest_tick_batch(batch(1, [(1000, 100.0)]))


def close_first_bar(engine, price):
    engine.ingest_snapshot({"symbol": "XAUUSD", "bars": {"M1": {
        "time": START, "open": 100.0, "high": max(110.0, price), "low": min(90.0, price),
        "close": price, "tick_volume": 100}}})


class IntrabarStrategyTests(unittest.TestCase):
    def test_z_peak_survives_retreat_before_close_and_confirms_next_bar(self):
        engine = engine_for()
        baseline(engine)
        peak = price_for(engine, 2.5001)
        retreat = price_for(engine, 2.2)
        engine.ingest_tick_batch(batch(2, [(10_000, peak), (50_000, retreat)]))
        self.assertEqual("ARMED_SELL", engine.state)
        self.assertEqual(0, engine.signal_sequence)
        self.assertAlmostEqual(2.5001, engine._trigger_z_extreme)
        close_first_bar(engine, retreat)
        current = price_for(engine, 2.2)
        result = engine.ingest_tick_batch(batch(3, [(61_000, current)]))
        self.assertEqual("TRIGGERED_SELL", result["state"])
        self.assertEqual(1, result["signal_sequence"])
        self.assertAlmostEqual(2.2, result["last_signal"]["trigger"]["z"]["current"])
        self.assertEqual(START + 60, result["last_signal"]["bar_time"])
        self.assertEqual("OBSERVED_TICKS_NEXT_BAR", result["last_signal"]["observation_mode"])
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["trading_enabled"])

    def test_buy_trough_is_symmetric(self):
        engine = engine_for("BUY")
        baseline(engine)
        engine.ingest_tick_batch(batch(2, [(10_000, price_for(engine, -2.6))]))
        close_first_bar(engine, price_for(engine, -2.2))
        result = engine.ingest_tick_batch(batch(3, [(61_000, price_for(engine, -2.2))]))
        self.assertEqual("TRIGGERED_BUY", result["state"])
        self.assertAlmostEqual(-2.6, result["last_signal"]["trigger"]["z"]["extreme"])

    def test_rsi_uses_observed_peak_not_last_close(self):
        engine = engine_for(indicator="rsi")
        baseline(engine)
        engine.ingest_tick_batch(batch(2, [(10_000, price_for(engine, 74.0, "rsi")),
                                           (50_000, price_for(engine, 68.0, "rsi"))]))
        self.assertEqual(0, engine.signal_sequence)
        close_first_bar(engine, price_for(engine, 68.0, "rsi"))
        result = engine.ingest_tick_batch(batch(3, [(61_000, price_for(engine, 70.0, "rsi"))]))
        self.assertEqual("TRIGGERED_SELL", result["state"])
        self.assertAlmostEqual(74.0, result["last_signal"]["trigger"]["rsi"]["extreme"])

    def test_and_latches_indicators_seen_at_different_observations(self):
        engine = engine_for()
        engine.profile["pullback"]["rsi_enabled"] = True
        baseline(engine)
        actual_metrics, warmup, histories = engine._tick_metrics(START * 1000 + 10_000, 100)
        first, second = copy.deepcopy(actual_metrics), copy.deepcopy(actual_metrics)
        first["pullback"].update(z=2.6, rsi=60)
        second["pullback"].update(z=2.2, rsi=75)
        with patch.object(engine, "_tick_metrics", side_effect=[(first, warmup, histories), (second, warmup, histories)]):
            engine.ingest_tick_batch(batch(2, [(10_000, 100), (20_000, 101)]))
        self.assertEqual("ARMED_SELL", engine.state)
        self.assertEqual({"rsi": True, "z": True}, engine._tick_setup_latches["conditions"])

    def test_and_latches_do_not_mix_different_pullback_bars(self):
        engine = engine_for()
        engine.profile["pullback"]["rsi_enabled"] = True
        baseline(engine)
        metrics, warmup, histories = engine._tick_metrics(START * 1000 + 10_000, 100)
        first, second = copy.deepcopy(metrics), copy.deepcopy(metrics)
        first["pullback"].update(z=2.6, rsi=60)
        second["pullback"].update(z=2.2, rsi=75)
        with patch.object(engine, "_tick_metrics", side_effect=[(first, warmup, histories), (second, warmup, histories)]):
            engine.ingest_tick_batch(batch(2, [(10_000, 100), (61_000, 101)]))
        self.assertIsNone(engine.armed_side)

    def test_partial_and_latches_and_extrema_do_not_survive_direction_flip(self):
        engine = engine_for()
        engine.profile["strategy"]["allow_buy"] = True
        engine.profile["pullback"]["rsi_enabled"] = True
        baseline(engine)
        metrics, warmup, histories = engine._tick_metrics(START * 1000 + 10_000, 100)
        first, other_side, returned = (copy.deepcopy(metrics) for _ in range(3))
        first["pullback"].update(z=2.6, rsi=60)
        first["trigger"]["z"] = 4.0
        other_side["pullback"].update(z=0, rsi=50)
        returned["pullback"].update(z=2.2, rsi=75)
        returned["trigger"]["z"] = 2.0
        observations = [(m, warmup, histories) for m in (first, other_side, returned)]
        directions = [({"SELL"}, "SELL", None), ({"BUY"}, "BUY", None),
                      ({"SELL"}, "SELL", None)]
        with patch.object(engine, "_tick_metrics", side_effect=observations), \
                patch.object(engine, "_direction_sides", side_effect=directions):
            engine.ingest_tick_batch(batch(2, [(10_000, 100), (20_000, 100), (30_000, 100)]))
        self.assertIsNone(engine.armed_side)
        self.assertEqual({"SELL": {"rsi": True, "z": False}}, engine._tick_latches)
        self.assertEqual(2.0, engine._tick_candidate_extremes["SELL"]["z"])

    def test_first_or_reconnected_batch_never_replays_old_thresholds(self):
        engine = engine_for()
        extreme = price_for(engine, 3)
        engine.ingest_tick_batch(batch(1, [(10_000, extreme), (61_000, 100)]))
        self.assertEqual(0, engine.signal_sequence)
        self.assertIsNone(engine.armed_side)
        engine.ingest_tick_batch(batch(2, [(62_000, extreme)]))
        self.assertEqual("SELL", engine.armed_side)
        result = engine.ingest_tick_batch(batch(1, [(63_000, 100)], stream="new-connection"))
        self.assertIsNone(result["armed_side"])
        self.assertEqual("TICK_STREAM_BASELINE", result["last_reset_reason"])

    def test_sequence_gap_discards_latched_peak(self):
        engine = engine_for()
        baseline(engine)
        engine.ingest_tick_batch(batch(2, [(10_000, price_for(engine, 3))]))
        result = engine.ingest_tick_batch(batch(4, [(61_000, 100)]))
        self.assertEqual(0, result["signal_sequence"])
        self.assertIsNone(result["armed_side"])
        self.assertEqual("TICK_STREAM_GAP", result["last_reset_reason"])

    def test_incomplete_packet_and_skipped_trigger_bar_expire_setup(self):
        for discontinuity in (batch(3, [(61_000, 100)], complete=False), batch(3, [(181_000, 100)])):
            engine = engine_for()
            baseline(engine)
            engine.ingest_tick_batch(batch(2, [(10_000, price_for(engine, 3))]))
            result = engine.ingest_tick_batch(discontinuity)
            self.assertEqual(0, result["signal_sequence"])
            self.assertIsNone(result["armed_side"])

    def test_repeated_packet_and_same_millisecond_ticks_are_deterministic(self):
        engine = engine_for()
        baseline(engine)
        packet = batch(2, [(10_000, price_for(engine, 3)), (10_000, price_for(engine, 2.0))])
        result = engine.ingest_tick_batch(packet)
        count = result["intrabar"]["observed_ticks"]
        result2 = engine.ingest_tick_batch(packet)
        self.assertEqual(result, result2)
        self.assertEqual(2, count)
        self.assertAlmostEqual(3, result["intrabar"]["setup_extremes"]["z"])

    def test_ticks_do_not_mutate_closed_history_or_use_future_bar_close(self):
        control, future = engine_for(), engine_for()
        future.history["M1"].append(Bar(START, 100, 1000, 90, 1000))
        baseline(control)
        baseline(future)
        before = copy.deepcopy(future.history)
        packet = batch(2, [(10_000, price_for(control, 3))])
        expected, actual = control.ingest_tick_batch(packet), future.ingest_tick_batch(packet)
        self.assertEqual(expected["indicators"], actual["indicators"])
        self.assertEqual(expected["intrabar"]["setup_extremes"], actual["intrabar"]["setup_extremes"])
        self.assertEqual(before, future.history)

    def test_triggered_setup_does_not_repeat_signal_on_more_ticks(self):
        engine = engine_for()
        baseline(engine)
        engine.ingest_tick_batch(batch(2, [(10_000, price_for(engine, 3))]))
        close_first_bar(engine, 105)
        price = price_for(engine, 2.6)
        engine.ingest_tick_batch(batch(3, [(61_000, price), (62_000, price), (63_000, price)]))
        self.assertEqual(1, engine.signal_sequence)
        engine.ingest_tick_batch(batch(4, [(64_000, price), (65_000, 100), (66_000, 100)]))
        self.assertEqual(1, engine.signal_sequence)

    def test_invalid_batch_rejected_atomically(self):
        engine = engine_for()
        baseline(engine)
        before = engine.status_payload(market_connected=True)
        for packet in (batch(2, [(20_000, 100), (10_000, 100)]),
                       batch(2, [(20_000, math.nan)]), batch(True, []), batch(2, [], stream="")):
            with self.assertRaises(StrategyDataError):
                engine.ingest_tick_batch(packet)
            self.assertEqual(before, engine.status_payload(market_connected=True))

    def test_profile_reset_and_status_mutation_cannot_reuse_extremes(self):
        engine = engine_for()
        baseline(engine)
        result = engine.ingest_tick_batch(batch(2, [(10_000, price_for(engine, 3))]))
        result["intrabar"]["setup_extremes"]["z"] = 100
        self.assertAlmostEqual(3, engine._trigger_z_extreme)
        changed = copy.deepcopy(engine.profile)
        changed["profile"]["name"] = "New profile"
        engine.set_profile(changed)
        result = engine.ingest_tick_batch(batch(3, [(61_000, 100)]))
        self.assertIsNone(result["armed_side"])
        self.assertEqual(0, result["signal_sequence"])

    def test_closed_bar_mode_ignores_tick_pipeline(self):
        engine = engine_for()
        engine.profile["trigger"]["confirm_closed_bar"] = True
        before = engine.status_payload(market_connected=True)
        self.assertEqual(before, engine.ingest_tick_batch(batch(1, [(10_000, 1000)])))

    def test_ohlc_backtest_explicitly_rejects_intrabar_tick_claims(self):
        with self.assertRaisesRegex(BacktestError, "requires observed real ticks"):
            BacktestEngine(profile(), initial_balance=10_000, spread_pips=10, commission_per_lot=0)

    def test_exact_z_and_rsi_reversal_boundaries_include_roundoff_only(self):
        engine = engine_for()
        engine.profile["trigger"].update(rsi_enabled=True, rsi_reversal_delta=0.3)
        engine._trigger_z_extreme = 2.5
        engine._trigger_rsi_extreme = 70.5
        passed, detail = engine._trigger_pass("SELL", {"trigger": {"z": 2.2, "rsi": 70.2}})
        self.assertTrue(passed)
        self.assertTrue(detail["z"]["passed"])
        self.assertTrue(detail["rsi"]["passed"])
        passed, _ = engine._trigger_pass("SELL", {"trigger": {"z": 2.20000001, "rsi": 70.20000001}})
        self.assertFalse(passed)

    def test_cached_forming_rsi_matches_full_closed_prefix_recalculation(self):
        engine = engine_for(indicator="rsi")
        closes = [bar.close for bar in engine.history["M1"]]
        for bid in (90, 100, 110, 97, 108):
            actual, _, _ = engine._tick_metrics(START * 1000 + 10_000, bid)
            self.assertAlmostEqual(_rsi(closes + [bid], 14), actual["trigger"]["rsi"], places=12)

    def test_missing_just_closed_bar_cannot_confirm_or_reuse_old_peak(self):
        engine = engine_for()
        baseline(engine)
        engine.ingest_tick_batch(batch(2, [(10_000, price_for(engine, 3))]))
        result = engine.ingest_tick_batch(batch(3, [(61_000, 100), (62_000, 100)]))
        self.assertEqual("WARMUP", result["state"])
        self.assertIn("history:M1:CLOSED_BAR_PENDING", result["warmup_reasons"])
        self.assertIsNone(result["armed_side"])
        self.assertEqual(0, result["signal_sequence"])
        close_first_bar(engine, 100)
        result = engine.ingest_tick_batch(batch(4, [(63_000, 100)]))
        self.assertEqual(0, result["signal_sequence"])
        self.assertIsNone(result["armed_side"])

    def test_setup_expires_after_configured_number_of_following_trigger_bars(self):
        engine = engine_for()
        engine.profile["entry"]["max_signal_age_bars"] = 1
        baseline(engine)
        engine.ingest_tick_batch(batch(2, [(10_000, price_for(engine, 3))]))
        close_first_bar(engine, 105)
        engine.ingest_tick_batch(batch(3, [(61_000, price_for(engine, 3))]))
        engine.ingest_snapshot({"symbol": "XAUUSD", "bars": {"M1": {
            "time": START + 60, "open": 105, "high": 105, "low": 105, "close": 105}}})
        result = engine.ingest_tick_batch(batch(4, [(121_000, price_for(engine, 2))]))
        self.assertEqual(0, result["signal_sequence"])
        self.assertIsNone(result["armed_side"])
        self.assertEqual("INTRABAR_SETUP_EXPIRED", result["blocked_reason"])

    def test_zero_quote_observation_does_not_manufacture_extreme(self):
        engine = engine_for()
        baseline(engine)
        packet = batch(2, [(10_000, 0)])
        result = engine.ingest_tick_batch(packet)
        self.assertEqual(0, result["intrabar"]["observed_ticks"])
        self.assertIsNone(result["armed_side"])
        self.assertEqual(START * 1000 + 10_000, result["intrabar"]["last_tick_time_msc"])

    def test_closed_prefix_cache_reused_but_invalidated_by_new_snapshot(self):
        engine = engine_for(indicator="rsi")
        with patch.object(engine, "_metrics", wraps=engine._metrics) as full_metrics:
            for index in range(100):
                engine._tick_metrics(START * 1000 + index, 99 + index / 100)
            self.assertEqual(1, full_metrics.call_count)
            close_first_bar(engine, 102)
            engine._tick_metrics((START + 60) * 1000, 101)
            self.assertGreaterEqual(full_metrics.call_count, 2)
            values = [bar.close for bar in engine.history["M1"]] + [101]
            metrics, _, _ = engine._tick_metrics((START + 60) * 1000 + 1, 101)
            self.assertAlmostEqual(_rsi(values, 14), metrics["trigger"]["rsi"], places=12)


if __name__ == "__main__":
    unittest.main()
