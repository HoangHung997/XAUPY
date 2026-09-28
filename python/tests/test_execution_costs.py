from copy import deepcopy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from xaupy_engine.backtest import BacktestEngine
from xaupy_engine.execution_costs import entry_cost_plan
from test_task011_backtest import test_profile, bars_for_trigger, dataset_from_bars


class EntryCostsTests(unittest.TestCase):
    def replay(self, profile):
        return BacktestEngine(profile, initial_balance=10000, spread_pips=20, commission_per_lot=7).run(
            dataset_from_bars(bars_for_trigger()), from_date="2024-01-01", to_date="2024-01-01")

    def test_profile_guards_block_actual_replay_entries(self):
        profile = test_profile()
        profile["costs"].update(max_spread_price_units=.5, max_commission_per_lot=7, min_net_rr=1.2, max_slippage_points=0)
        self.assertGreater(len(self.replay(profile)["trades"]), 0)
        for change in ({"max_spread_price_units": .1}, {"max_commission_per_lot": 6},
                       {"min_net_rr": 100}, {"max_slippage_points": 300}):
            with self.subTest(change=change):
                restricted = deepcopy(profile)
                restricted["costs"].update(change)
                self.assertEqual([], self.replay(restricted)["trades"])

    def test_net_rr_and_sizing_reserve_both_slippage_and_fees(self):
        profile = test_profile()
        profile["costs"].update(max_commission_per_lot=10, max_slippage_points=20)
        plan = entry_cost_plan(profile, risk_distance=2, target_distance=4, spread_price=.1,
                               point=.01, tick_size=.01, tick_value=1)
        self.assertAlmostEqual(230, plan.loss_per_lot)
        self.assertAlmostEqual(370, plan.reward_per_lot)
        self.assertAlmostEqual(370 / 230, plan.net_rr)
        profile["risk"].update(sizing_mode="RISK_PERCENT", risk_percent=.5, max_lot=1)
        engine = BacktestEngine(profile, initial_balance=10000, spread_pips=10, commission_per_lot=7)
        metadata = dataset_from_bars(bars_for_trigger()).metadata
        volume = engine._position_volume(10000, metadata, 2, loss_per_lot=plan.loss_per_lot)
        self.assertLessEqual(volume * plan.loss_per_lot, 50)
        self.assertGreater((volume + metadata.volume_step) * plan.loss_per_lot, 50)

    def test_boundary_and_zero_spread_are_not_rejected_by_rounding(self):
        profile = test_profile()
        profile["costs"].update(max_spread_price_units=0, max_commission_per_lot=0, min_net_rr=1, max_slippage_points=0)
        plan = entry_cost_plan(profile, risk_distance=2, target_distance=2, spread_price=0,
                               point=.01, tick_size=.01, tick_value=1, actual_commission_per_lot=0)
        self.assertIsNone(plan.blocker)


if __name__ == "__main__":
    unittest.main()
