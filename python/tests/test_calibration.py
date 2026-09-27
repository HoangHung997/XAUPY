from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xaupy_engine.calibration import Candidate, collect_events, rsi_series, select_candidate, z_series
from xaupy_engine.config_schema import default_profile
from xaupy_engine.optimizer import OptimizerError, parse_parameter_ranges
from xaupy_engine.strategy_engine import Bar, _rsi, _zscore


class CalibrationTests(unittest.TestCase):
    def test_provisional_indicators_match_canonical_engine_without_future_data(self):
        rng = random.Random(317)
        price = 4000.0
        bars = []
        for i in range(160):
            close = price + rng.uniform(-2, 2)
            bars.append(Bar(1704067200 + i*60, price, max(price, close)+.8,
                            min(price, close)-.6, close))
            price = close
        for period in (7, 14, 21):
            result = rsi_series(bars, period)
            z_result = z_series(bars, period)
            for i in range(period, len(bars)):
                for j, value in enumerate((bars[i].high, bars[i].low, bars[i].close)):
                    prefix = [b.close for b in bars[:i]] + [value]
                    self.assertAlmostEqual(_rsi(prefix, period), result[j][i], places=10)
                    self.assertAlmostEqual(_zscore(prefix, period), z_result[j][i], places=9)
        # Mutating future bars cannot change any earlier provisional indicator.
        later = bars[:80] + [Bar(b.time, 99999, 99999, 99999, 99999) for b in bars[80:]]
        self.assertEqual(rsi_series(bars, 14)[2][14:80], rsi_series(later, 14)[2][14:80])
        self.assertEqual(z_series(bars, 20)[2][19:80], z_series(later, 20)[2][19:80])

    def test_touch_is_retained_when_arm_candle_closes_below_threshold(self):
        bars = [Bar(1704067200+i*60, 100+i, 102+i, 99+i, 101+i) for i in range(12)]
        z = ([0., 2.6, 2.3] + [0.]*9, [0.]*12, [0., 2., 2.2]+[0.]*9)
        rsi = tuple([50.]*12 for _ in range(3))
        kwargs = dict(start=0, end=12, point_size=.01, horizon=2)
        events = collect_events(bars, [20.]*12, Candidate("Z"), rsi, z, **kwargs)
        self.assertEqual(1, len(events))
        event = events[0]
        self.assertEqual((1, 2, 3, 4, -1), (event.arm, event.confirmation, event.entry, event.exit, event.side))
        self.assertAlmostEqual(.2, event.cost)
        self.assertEqual([], collect_events(bars, [20.]*12, Candidate("Z"), rsi, z,
                                           use_extremes=False, **kwargs))

    def test_no_setup_or_return_crosses_sample_boundary(self):
        bars = [Bar(1704067200+i*60, 100, 102, 99, 101) for i in range(12)]
        z = ([0., 2.6, 2.3]+[0.]*9, [0.]*12, [0., 2., 2.2]+[0.]*9)
        rsi = tuple([50.]*12 for _ in range(3))
        self.assertEqual([], collect_events(bars, [0.]*12, Candidate("Z"), rsi, z,
                                           start=2, end=12, point_size=.01, horizon=2))
        self.assertEqual([], collect_events(bars, [0.]*12, Candidate("Z"), rsi, z,
                                           start=0, end=4, point_size=.01, horizon=2))

    def test_selection_never_uses_heldout_performance(self):
        rows = [{"id": i, "train": {"events": 60, "lower_mean_95": v},
                 "validation": {"mean_net_price": -999}, "test": {"mean_net_price": -999}}
                for i, v in enumerate((.1, .3, .2))]
        self.assertEqual(1, select_candidate(rows)["id"])
        rows[0]["validation"]["mean_net_price"] = 1e9
        rows[0]["test"]["mean_net_price"] = 1e9
        self.assertEqual(1, select_candidate(rows)["id"])

    def test_gap_between_arm_confirmation_or_outcome_invalidates_event(self):
        base = 1704067200
        rsi = tuple([50.]*12 for _ in range(3))
        z = ([0., 2.6, 2.3]+[0.]*9, [0.]*12, [0., 2., 2.2]+[0.]*9)
        for gap_start in (2, 3, 4):
            bars = [Bar(base+i*60+(86400 if i >= gap_start else 0), 100, 102, 99, 101) for i in range(12)]
            self.assertEqual([], collect_events(bars, [0.]*12, Candidate("Z"), rsi, z,
                                               start=0, end=12, point_size=.01, horizon=2))

    def test_optimizer_exposes_z_levels_only_when_enabled(self):
        profile = default_profile()
        raw = [{"path": "pullback.z_sell_level", "min": 2., "max": 2.5, "step": .5}]
        with self.assertRaises(OptimizerError):
            parse_parameter_ranges(raw, profile)
        profile["pullback"]["z_enabled"] = True
        self.assertEqual((2., 2.5), parse_parameter_ranges(raw, profile)[0].values)


if __name__ == "__main__":
    unittest.main()
