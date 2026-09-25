import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.config_schema import TIMEFRAME_OPTIONS, default_profile
from xaupy_engine.strategy_engine import (
    Bar,
    StrategyEngine,
    _adx,
    _atr,
    _moving_average,
    _rsi,
    _zscore,
)


def test_profile():
    profile = default_profile()
    profile["direction"]["ma_period"] = 3
    profile["pullback"]["rsi_period"] = 2
    profile["pullback"]["rsi_buy_level"] = 40.0
    profile["pullback"]["rsi_sell_level"] = 60.0
    profile["pullback"]["z_enabled"] = False
    profile["trigger"]["rsi_period"] = 2
    profile["trigger"]["rsi_reversal_delta"] = 10.0
    profile["trigger"]["z_enabled"] = False
    profile["filters"]["adx"]["enabled"] = False
    profile["filters"]["atr"]["enabled"] = False
    profile["filters"]["open"]["enabled"] = False
    profile["direction"]["open_filter_enabled"] = False
    return profile


def snapshot(index, *, direction_close, pullback_close, trigger_close, profile=None):
    profile = profile or test_profile()
    selected = {
        profile["timeframes"]["direction"]: direction_close,
        profile["timeframes"]["pullback"]: pullback_close,
        profile["timeframes"]["trigger"]: trigger_close,
    }
    bars = {}
    timestamp = 1_800_000_000 + (index * 60)
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
        "symbol": profile["strategy"]["symbol"],
        "bars": bars,
    }


class IndicatorTests(unittest.TestCase):
    def test_core_indicator_math_is_deterministic(self):
        self.assertAlmostEqual(3.0, _moving_average([1, 2, 3, 4], 3, "SMA"))
        self.assertAlmostEqual(3.25, _moving_average([1, 2, 3, 4], 3, "EMA"))
        self.assertAlmostEqual(100.0, _rsi([1, 2, 3], 2))
        self.assertGreater(_zscore([1, 2, 3], 3), 1.2)

        bars = [
            Bar(1, 10.0, 11.0, 9.0, 10.0),
            Bar(2, 10.0, 12.0, 10.0, 11.0),
            Bar(3, 11.0, 13.0, 11.0, 12.0),
        ]
        self.assertAlmostEqual(2.0, _atr(bars, 2))

    def test_adx_reports_strong_monotonic_trend(self):
        bars = []
        for index in range(12):
            close = 100.0 + index
            bars.append(Bar(index + 1, close - 0.2, close + 0.5, close - 0.5, close))
        value = _adx(bars, 3)
        self.assertIsNotNone(value)
        self.assertGreater(value, 90.0)


class StrategyStateMachineTests(unittest.TestCase):
    def test_buy_pipeline_arms_then_triggers_once(self):
        profile = test_profile()
        engine = StrategyEngine(profile)

        direction = [100, 101, 102, 103, 104, 105]
        pullback = [100, 99, 98, 97, 96, 95]
        trigger = [100, 99, 98, 97, 96, 98]

        states = []
        for index in range(len(direction)):
            result = engine.ingest_snapshot(
                snapshot(
                    index,
                    direction_close=direction[index],
                    pullback_close=pullback[index],
                    trigger_close=trigger[index],
                    profile=profile,
                )
            )
            states.append(result["state"])

        self.assertIn("ARMED_BUY", states)
        self.assertEqual("TRIGGERED_BUY", states[-1])
        self.assertEqual("BUY", engine.direction)
        self.assertEqual(1, engine.signal_sequence)
        self.assertEqual("BUY", engine.last_signal["side"])
        self.assertFalse(engine.last_signal["indicators"]["trigger"]["rsi"] is None)

        duplicate = engine.ingest_snapshot(
            snapshot(
                len(direction) - 1,
                direction_close=direction[-1],
                pullback_close=pullback[-1],
                trigger_close=trigger[-1],
                profile=profile,
            )
        )
        self.assertEqual("TRIGGERED_BUY", duplicate["state"])
        self.assertEqual(1, engine.signal_sequence)

    def test_sell_pipeline_is_symmetric(self):
        profile = test_profile()
        engine = StrategyEngine(profile)

        direction = [105, 104, 103, 102, 101, 100]
        pullback = [100, 101, 102, 103, 104, 105]
        trigger = [100, 101, 102, 103, 104, 102]

        for index in range(len(direction)):
            result = engine.ingest_snapshot(
                snapshot(
                    index,
                    direction_close=direction[index],
                    pullback_close=pullback[index],
                    trigger_close=trigger[index],
                    profile=profile,
                )
            )

        self.assertEqual("TRIGGERED_SELL", result["state"])
        self.assertEqual("SELL", engine.direction)
        self.assertEqual(1, engine.signal_sequence)
        self.assertEqual("SELL", engine.last_signal["side"])

    def test_no_trigger_occurs_on_the_same_bar_that_arms_pullback(self):
        profile = test_profile()
        engine = StrategyEngine(profile)

        for index, values in enumerate(
            [
                (100, 100, 100),
                (101, 99, 99),
                (102, 98, 98),
            ]
        ):
            result = engine.ingest_snapshot(
                snapshot(
                    index,
                    direction_close=values[0],
                    pullback_close=values[1],
                    trigger_close=values[2],
                    profile=profile,
                )
            )

        self.assertEqual("ARMED_BUY", result["state"])
        self.assertEqual(0, engine.signal_sequence)
        self.assertIsNone(engine.last_signal)

    def test_independent_timeframes_are_consumed_from_profile(self):
        profile = test_profile()
        profile["timeframes"]["direction"] = "H4"
        profile["timeframes"]["pullback"] = "M3"
        profile["timeframes"]["trigger"] = "M15"
        engine = StrategyEngine(profile)

        for index in range(6):
            result = engine.ingest_snapshot(
                snapshot(
                    index,
                    direction_close=100 + index,
                    pullback_close=100 - index,
                    trigger_close=100 - index if index < 5 else 102,
                    profile=profile,
                )
            )

        indicators = result["indicators"]
        self.assertEqual("H4", indicators["direction"]["timeframe"])
        self.assertEqual("M3", indicators["pullback"]["timeframe"])
        self.assertEqual("M15", indicators["trigger"]["timeframe"])
        self.assertEqual("TRIGGERED_BUY", result["state"])

    def test_profile_change_resets_setup_but_retains_market_history(self):
        profile = test_profile()
        engine = StrategyEngine(profile)

        for index in range(3):
            engine.ingest_snapshot(
                snapshot(
                    index,
                    direction_close=100 + index,
                    pullback_close=100 - index,
                    trigger_close=100 - index,
                    profile=profile,
                )
            )

        self.assertEqual("ARMED_BUY", engine.state)
        before = copy.deepcopy(engine.status_payload(market_connected=True)["bars_seen"])

        changed = copy.deepcopy(profile)
        changed["profile"]["name"] = "Changed"
        engine.set_profile(changed)

        after = engine.status_payload(market_connected=True)
        self.assertEqual("WARMUP", after["state"])
        self.assertEqual("PROFILE_CHANGED", after["last_reset_reason"])
        self.assertEqual(before, after["bars_seen"])
        self.assertIsNone(after["armed_side"])

    def test_stale_projection_never_presents_strategy_as_live(self):
        profile = test_profile()
        engine = StrategyEngine(profile)
        for index in range(3):
            engine.ingest_snapshot(
                snapshot(
                    index,
                    direction_close=100 + index,
                    pullback_close=100 - index,
                    trigger_close=100 - index,
                    profile=profile,
                )
            )

        stale = engine.status_payload(market_connected=False)
        self.assertFalse(stale["available"])
        self.assertFalse(stale["ready"])
        self.assertEqual("STALE", stale["state"])
        self.assertEqual("BRIDGE_STALE", stale["blocked_reason"])
        self.assertFalse(stale["trading_enabled"])
        self.assertFalse(stale["execution_enabled"])


if __name__ == "__main__":
    unittest.main()
