from copy import deepcopy
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xaupy_engine.config_schema import default_profile
from xaupy_engine.strategy_engine import Bar, StrategyDataError, StrategyEngine, _rsi, _zscore


START = 1_800_000_000


def engine_for(*, closed=True):
    profile = default_profile()
    profile["timeframes"] = {role: "M1" for role in ("direction", "pullback", "trigger")}
    profile["direction"]["ma_enabled"] = False
    profile["pullback"].update(rsi_enabled=True, rsi_period=7, z_enabled=False, z_period=11)
    profile["trigger"].update(confirm_closed_bar=closed, rsi_enabled=False, rsi_period=14,
                              z_enabled=True, z_period=20, z_reversal_delta=.3)
    engine = StrategyEngine(profile)
    values = [99.0, 101.0] * 20
    engine.history["M1"] = [Bar(START - (40 - i) * 60, price, price, price, price) for i, price in enumerate(values)]
    engine._evaluate({"M1"})
    return engine


def ticks(sequence, rows, *, stream="display-stream", complete=True, **extra):
    return {"symbol": "XAUUSD", "server_time": START + 600,
            "tick_batch": {"stream_id": stream, "sequence": sequence, "complete": complete,
                           "ticks": [{"time_msc": START * 1000 + offset, "bid": bid, "ask": bid + .2}
                                     for offset, bid in rows]}, **extra}


def decisions(engine):
    value = engine.status_payload(market_connected=True)
    value.pop("display")
    value.pop("intrabar")
    return value


class TickDisplayTests(unittest.TestCase):
    def test_closed_mode_updates_configured_rsi_and_z_even_when_gate_disabled(self):
        engine = engine_for()
        original = decisions(engine)
        closes = [bar.close for bar in engine.history["M1"]]
        for sequence, bid in enumerate((100, 103, 99.7), start=1):
            display = engine.ingest_tick_batch(ticks(sequence, [(sequence * 1000, bid)]))["display"]
            self.assertTrue(display["available"])
            self.assertEqual("CLOSED_BAR", display["confirmation_mode"])
            for role in ("pullback", "trigger"):
                self.assertAlmostEqual(_rsi(closes + [bid], engine.profile[role]["rsi_period"]), display["indicators"][role]["rsi"])
                self.assertAlmostEqual(_zscore(closes + [bid], engine.profile[role]["z_period"]), display["indicators"][role]["z"])
            self.assertEqual(original, decisions(engine))
        self.assertIsNone(engine.last_metrics["pullback"]["z"])
        self.assertIsNone(engine.last_metrics["trigger"]["rsi"])

    def test_tick_discontinuity_never_resets_closed_bar_decisions(self):
        engine = engine_for()
        original = decisions(engine)
        for payload in (ticks(1, [(1000, 108)]), ticks(2, [(2000, 90)], complete=False),
                        ticks(4, [(3000, 108)]), ticks(1, [(4000, 100)], stream="reconnected")):
            display = engine.ingest_tick_batch(payload)["display"]
            self.assertFalse(display["continuous"])
            self.assertEqual(original, decisions(engine))

    def test_observed_current_bar_preserves_equal_ms_order_and_is_explicitly_partial(self):
        engine = engine_for()
        engine.ingest_tick_batch(ticks(1, [(1000, 100)]))
        display = engine.ingest_tick_batch(ticks(2, [(2000, 103), (2000, 98), (2000, 101)]))["display"]
        bar = display["current_bars"]["M1"]
        self.assertEqual((START, 100, 103, 98, 101), tuple(bar[k] for k in ("time", "open", "high", "low", "close")))
        self.assertEqual(4, bar["observed_ticks"])
        self.assertTrue(bar["partial"])
        self.assertEqual("OBSERVED_TICKS", bar["source"])
        self.assertEqual(START * 1000 + 2000, display["tick_time_msc"])
        self.assertEqual(101.2, display["ask"])

    def test_duplicate_batches_do_not_move_quote_extrema_or_counts(self):
        engine = engine_for()
        before = engine.ingest_tick_batch(ticks(1, [(1000, 100)]))["display"]
        after = engine.ingest_tick_batch(ticks(1, [(2000, 999)]))["display"]
        self.assertEqual(before, after)

    def test_invalid_batch_is_atomic_also_in_closed_mode(self):
        engine = engine_for()
        before = engine.ingest_tick_batch(ticks(1, [(1000, 100)]))
        with self.assertRaises(StrategyDataError):
            engine.ingest_tick_batch(ticks(2, [(2000, 102), (1900, 99)]))
        self.assertEqual(before, engine.status_payload(market_connected=True))

    def test_zero_quote_records_do_not_fabricate_price_or_quote_timestamp(self):
        engine = engine_for()
        before = engine.ingest_tick_batch(ticks(1, [(1000, 100)]))["display"]
        payload = ticks(2, [(2000, 0)])
        payload["tick_batch"]["ticks"][0]["ask"] = 0
        after = engine.ingest_tick_batch(payload)["display"]
        for key in ("tick_time_msc", "bid", "ask", "current_bars", "observed_ticks", "indicators"):
            self.assertEqual(before[key], after[key])

    def test_missing_just_closed_bar_hides_current_indicators_until_history_arrives(self):
        engine = engine_for()
        engine.ingest_tick_batch(ticks(1, [(1000, 100)]))
        display = engine.ingest_tick_batch(ticks(2, [(61000, 102)]))["display"]
        self.assertFalse(display["indicators_ready"])
        self.assertIn("history:M1:CLOSED_BAR_PENDING", display["warmup_reasons"])
        self.assertIsNone(display["indicators"]["pullback"]["rsi"])
        self.assertIsNone(display["indicators"]["trigger"]["z"])
        engine.ingest_snapshot({"symbol": "XAUUSD", "bars": {"M1": {"time": START, "open": 100, "high": 103, "low": 99, "close": 101}}})
        display = engine.ingest_tick_batch(ticks(3, [(62000, 102)]))["display"]
        self.assertTrue(display["indicators_ready"])
        self.assertIsNotNone(display["indicators"]["trigger"]["z"])

    def test_future_closed_bars_and_current_bar_ohlc_are_not_used_for_prior_ticks(self):
        engine, control = engine_for(), engine_for()
        engine.history["M1"].append(Bar(START, 1, 10000, 1, 9999))
        future_bars = {"M1": {"time": START, "open": 1, "high": 10000, "low": 1, "close": 9999}}
        actual = engine.ingest_tick_batch(ticks(1, [(1000, 102)], current_bars=future_bars))["display"]
        expected = control.ingest_tick_batch(ticks(1, [(1000, 102)]))["display"]
        self.assertEqual(expected["indicators"], actual["indicators"])
        self.assertEqual(expected["current_bars"], actual["current_bars"])

    def test_disconnect_and_profile_change_clear_display_without_using_old_period(self):
        engine = engine_for()
        engine.ingest_tick_batch(ticks(1, [(1000, 103)]))
        stale = engine.status_payload(market_connected=False)["display"]
        self.assertFalse(stale["available"])
        self.assertEqual({}, stale["indicators"])
        self.assertEqual({}, stale["current_bars"])
        profile = deepcopy(engine.profile)
        profile["trigger"]["z_period"] = 5
        engine.set_profile(profile)
        self.assertFalse(engine.status_payload(market_connected=True)["display"]["available"])
        display = engine.ingest_tick_batch(ticks(2, [(2000, 103)]))["display"]
        self.assertAlmostEqual(_zscore([b.close for b in engine.history["M1"]] + [103], 5), display["indicators"]["trigger"]["z"])
        self.assertEqual(1, display["observed_ticks"])

    def test_closed_candle_strategy_outputs_identical_with_or_without_tick_display(self):
        observed, control = engine_for(), engine_for()
        observed.ingest_tick_batch(ticks(1, [(1000, 100)]))
        for i, price in enumerate((105, 102, 101, 104, 103), start=1):
            observed.ingest_tick_batch(ticks(i + 1, [((i * 60 - 1) * 1000, 1000 - i)]))
            bar = {"time": START + (i - 1) * 60, "open": price, "high": price, "low": price, "close": price}
            payload = {"symbol": "XAUUSD", "bars": {"M1": bar}}
            observed.ingest_snapshot(payload)
            control.ingest_snapshot(payload)
            self.assertEqual(decisions(control), decisions(observed))

    def test_intrabar_decision_and_display_share_enabled_indicator_value(self):
        engine = engine_for(closed=False)
        engine.ingest_tick_batch(ticks(1, [(1000, 100)]))
        value = engine.ingest_tick_batch(ticks(2, [(2000, 103)]))
        self.assertEqual(value["indicators"]["trigger"]["z"], value["display"]["indicators"]["trigger"]["z"])
        self.assertIsNotNone(value["display"]["indicators"]["trigger"]["rsi"])
        self.assertIsNone(value["indicators"]["trigger"]["rsi"])
        self.assertFalse(value["trading_enabled"])

    def test_thousand_tick_batch_with_long_history_uses_one_closed_prefix_cache(self):
        engine = engine_for()
        engine.history["M1"] = [Bar(START - (4096 - i) * 60, 100, 101, 99, 99 + i % 3) for i in range(4096)]
        engine.ingest_tick_batch(ticks(1, [(1000, 100)]))
        from unittest.mock import patch
        with patch.object(engine, "_metrics", wraps=engine._metrics) as metrics:
            started = time.perf_counter()
            display = engine.ingest_tick_batch(ticks(2, [(2000 + i, 100 + (i % 7) * .1) for i in range(1000)]))["display"]
            elapsed = time.perf_counter() - started
        self.assertEqual(0, metrics.call_count)  # Baseline built the closed prefix once.
        self.assertEqual(1001, display["observed_ticks"])
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
