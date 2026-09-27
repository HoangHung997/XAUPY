from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.backtest import (
    BacktestEngine,
    BacktestState,
    DatasetMetadata,
    HistoricalDataset,
    OpenPosition,
    PendingStopEntry,
)
from xaupy_engine.config_schema import default_profile
from xaupy_engine.optimizer import OptimizerError, parse_parameter_ranges
from xaupy_engine.strategy_engine import Bar, StrategyEngine, _atr


def make_profile() -> dict:
    profile = default_profile()
    profile["profile"]["name"] = "Task013 Test"
    profile["strategy"]["allow_buy"] = True
    profile["strategy"]["allow_sell"] = True
    profile["timeframes"] = {
        "direction": "M1",
        "pullback": "M1",
        "trigger": "M1",
    }
    profile["direction"]["ma_enabled"] = False
    profile["direction"]["open_filter_enabled"] = False
    profile["pullback"]["rsi_enabled"] = False
    profile["pullback"]["z_enabled"] = False
    profile["trigger"]["rsi_enabled"] = False
    profile["trigger"]["rsi_period"] = 2
    profile["trigger"]["rsi_reversal_delta"] = 1.0
    profile["trigger"]["z_enabled"] = False
    profile["trigger"]["z_period"] = 3
    profile["trigger"]["z_reversal_delta"] = 0.25
    profile["filters"]["adx"]["enabled"] = False
    profile["filters"]["atr"]["enabled"] = False
    profile["filters"]["open"]["enabled"] = False
    profile["risk"]["sizing_mode"] = "FIXED_LOT"
    profile["risk"]["fixed_lot"] = 0.10
    profile["risk"]["max_lot"] = 1.0
    profile["risk"]["max_open_positions"] = 2
    profile["risk"]["max_trades_per_day"] = 20
    profile["risk"]["cooldown_minutes"] = 0
    profile["risk"]["max_consecutive_losses"] = 20
    profile["risk"]["max_daily_loss_pct"] = 50.0
    profile["risk"]["stop_after_daily_target"] = False
    profile["stop_loss"]["mode"] = "FIXED"
    profile["stop_loss"]["fixed_price_units"] = 2.0
    profile["stop_loss"]["min_price_units"] = 0.1
    profile["stop_loss"]["max_price_units"] = 50.0
    profile["take_profit"]["mode"] = "FIXED"
    profile["take_profit"]["fixed_price_units"] = 3.0
    profile["management"]["breakeven_enabled"] = False
    profile["management"]["partial_close_enabled"] = False
    profile["management"]["trailing_enabled"] = False
    profile["management"]["sl_tighten_mode"] = "OFF"
    profile["sessions"]["timezone"] = "UTC"
    profile["sessions"]["session1_enabled"] = False
    profile["sessions"]["session2_enabled"] = False
    profile["news"]["enabled"] = False
    return profile


def metadata() -> DatasetMetadata:
    return DatasetMetadata(
        symbol="XAUUSD",
        point_size=0.01,
        tick_size=0.01,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        timezone_offset_minutes=0,
    )


def dataset(bars: list[Bar] | None = None) -> HistoricalDataset:
    if bars is None:
        bars = [
            Bar(1_704_067_200, 100, 101, 99, 100, 100),
            Bar(1_704_067_260, 100, 101, 99, 100, 100),
        ]
    return HistoricalDataset(
        path=pathlib.Path("task013.json"),
        fingerprint="d" * 64,
        metadata=metadata(),
        bars=tuple(bars),
    )


def engine(profile: dict | None = None, commission: float = 0.0) -> BacktestEngine:
    return BacktestEngine(
        profile or make_profile(),
        initial_balance=10_000,
        spread_pips=0,
        commission_per_lot=commission,
    )


def open_position(
    *,
    side: str = "BUY",
    entry: float = 100.0,
    sl: float = 98.0,
    original_tp: float = 103.0,
    hard_tp: float = 110.0,
    volume: float = 0.10,
) -> OpenPosition:
    return OpenPosition(
        trade_id=1,
        signal_sequence=1,
        signal_time=1_704_067_200,
        side=side,
        entry_time=1_704_067_260,
        entry_price=entry,
        volume=volume,
        sl=sl,
        tp=hard_tp,
        original_sl=sl,
        original_risk=abs(entry - sl),
        profile_hash="p" * 64,
        dataset_fingerprint="d" * 64,
        initial_volume=volume,
        original_tp=original_tp,
        hard_tp=hard_tp,
        signal_trigger_rsi=45.0,
        signal_trigger_z=-0.5,
    )


class StopConfirmTests(unittest.TestCase):
    def test_stop_confirm_uses_signal_bar_extreme_and_fills_touch(self):
        profile = make_profile()
        profile["entry"]["mode"] = "STOP_CONFIRM"
        profile["entry"]["pending_buffer_price_units"] = 0.10
        profile["entry"]["cancel_on_direction_change"] = True
        bt = engine(profile)
        strategy = StrategyEngine(profile)
        signal_bar = Bar(1_704_067_200, 99.5, 100.0, 98.5, 99.8, 100)
        strategy.history["M1"] = [signal_bar]
        strategy.direction = "BUY"
        state = BacktestState(balance=10_000, peak_equity=10_000)
        current = Bar(1_704_067_260, 99.9, 100.4, 99.6, 100.2, 100)
        signal = {
            "sequence": 7,
            "side": "BUY",
            "bar_time": signal_bar.time,
            "detected_close_time": signal_bar.time + 60,
            "profile_hash": strategy.profile_hash,
            "indicators": {"trigger": {"rsi": 45.0, "z": -0.5}},
        }

        bt._try_open_signal(
            state,
            strategy,
            dataset([signal_bar, current]),
            current,
            signal,
            0.0,
        )
        self.assertEqual(1, len(state.pending_entries))
        self.assertAlmostEqual(100.10, state.pending_entries[0].trigger_price)

        bt._process_pending_entries(
            state,
            strategy,
            dataset([signal_bar, current]),
            current,
            0.0,
        )
        self.assertEqual([], state.pending_entries)
        self.assertEqual(1, len(state.positions))
        self.assertEqual("STOP_CONFIRM", state.positions[0].entry_mode)
        self.assertAlmostEqual(100.10, state.positions[0].entry_price)
        self.assertAlmostEqual(100.10, state.positions[0].pending_trigger_price)

    def test_stop_confirm_gap_fills_at_executable_open(self):
        profile = make_profile()
        profile["entry"]["mode"] = "STOP_CONFIRM"
        profile["entry"]["pending_buffer_price_units"] = 0.0
        bt = engine(profile)
        strategy = StrategyEngine(profile)
        signal_bar = Bar(1_704_067_200, 99, 100, 98, 99.5, 100)
        strategy.history["M1"] = [signal_bar]
        strategy.direction = "BUY"
        state = BacktestState(balance=10_000, peak_equity=10_000)
        current = Bar(1_704_067_260, 101, 102, 100.5, 101.5, 100)
        signal = {
            "sequence": 1,
            "side": "BUY",
            "bar_time": signal_bar.time,
            "detected_close_time": signal_bar.time + 60,
            "profile_hash": strategy.profile_hash,
        }
        bt._try_open_signal(
            state, strategy, dataset([signal_bar, current]), current, signal, 0.0
        )
        bt._process_pending_entries(
            state, strategy, dataset([signal_bar, current]), current, 0.0
        )
        self.assertEqual(101.0, state.positions[0].entry_price)

    def test_pending_signal_expires_and_never_fills(self):
        profile = make_profile()
        bt = engine(profile)
        strategy = StrategyEngine(profile)
        strategy.direction = "BUY"
        state = BacktestState(balance=10_000, peak_equity=10_000)
        state.pending_entries.append(
            PendingStopEntry(
                signal_sequence=1,
                signal_time=100,
                detected_close_time=160,
                side="BUY",
                trigger_price=101.0,
                created_time=160,
                expires_at=220,
                signal_stale_at=1000,
                profile_hash="p" * 64,
                dataset_fingerprint="d" * 64,
            )
        )
        bar = Bar(220, 100, 105, 99, 104, 1)
        bt._process_pending_entries(state, strategy, dataset([bar]), bar, 0.0)
        self.assertEqual([], state.pending_entries)
        self.assertEqual(0, len(state.positions))
        self.assertEqual(1, state.skipped_signals["PENDING_EXPIRED"])

    def test_new_opposite_signal_cancels_existing_pending(self):
        profile = make_profile()
        profile["entry"]["mode"] = "STOP_CONFIRM"
        bt = engine(profile)
        strategy = StrategyEngine(profile)
        signal_bar = Bar(1_704_067_200, 100, 101, 99, 100, 1)
        strategy.history["M1"] = [signal_bar]
        strategy.direction = "BOTH"
        state = BacktestState(balance=10_000, peak_equity=10_000)
        current = Bar(1_704_067_260, 100, 100.2, 99.8, 100, 1)

        for sequence, side in ((1, "BUY"), (2, "SELL")):
            bt._try_open_signal(
                state,
                strategy,
                dataset([signal_bar, current]),
                current,
                {
                    "sequence": sequence,
                    "side": side,
                    "bar_time": signal_bar.time,
                    "detected_close_time": signal_bar.time + 60,
                    "profile_hash": strategy.profile_hash,
                },
                0.0,
            )

        self.assertEqual(["SELL"], [item.side for item in state.pending_entries])
        self.assertEqual(
            1,
            state.skipped_signals["PENDING_CANCEL_OPPOSITE_SETUP"],
        )

    def test_direction_change_cancels_pending_before_touch(self):
        profile = make_profile()
        bt = engine(profile)
        strategy = StrategyEngine(profile)
        strategy.direction = "SELL"
        state = BacktestState(balance=10_000, peak_equity=10_000)
        state.pending_entries.append(
            PendingStopEntry(
                signal_sequence=1,
                signal_time=100,
                detected_close_time=160,
                side="BUY",
                trigger_price=101,
                created_time=160,
                expires_at=1000,
                signal_stale_at=1000,
                profile_hash="p" * 64,
                dataset_fingerprint="d" * 64,
            )
        )
        bar = Bar(220, 100, 105, 99, 104, 1)
        bt._process_pending_entries(state, strategy, dataset([bar]), bar, 0.0)
        self.assertEqual([], state.pending_entries)
        self.assertEqual(
            1,
            state.skipped_signals["PENDING_CANCEL_DIRECTION_CHANGE"],
        )


class AtrAndTargetTests(unittest.TestCase):
    def test_atr_initial_stop_uses_only_closed_history(self):
        profile = make_profile()
        profile["stop_loss"]["mode"] = "ATR"
        profile["stop_loss"]["atr_timeframe"] = "M1"
        profile["stop_loss"]["atr_period"] = 2
        profile["stop_loss"]["atr_multiplier"] = 1.5
        profile["stop_loss"]["min_price_units"] = 0.1
        profile["stop_loss"]["max_price_units"] = 50.0
        bt = engine(profile)
        strategy = StrategyEngine(profile)
        bars = [
            Bar(60, 100, 101, 99, 100, 1),
            Bar(120, 100, 102, 99.5, 101, 1),
            Bar(180, 101, 103, 100, 102, 1),
            Bar(240, 102, 104, 101, 103, 1),
        ]
        strategy.history["M1"] = bars
        expected_atr = _atr(bars, 2)
        self.assertIsNotNone(expected_atr)

        sl, distance = bt._initial_stop(
            strategy,
            dataset(bars),
            "BUY",
            105.0,
            0.0,
        )
        self.assertAlmostEqual(expected_atr * 1.5, distance)
        self.assertAlmostEqual(105.0 - distance, sl)

    def test_dynamic_target_hard_cap_respects_emergency_server_tp(self):
        profile = make_profile()
        profile["take_profit"]["mode"] = "ZRSI_DYNAMIC"
        profile["take_profit"]["fixed_price_units"] = 3.0
        profile["take_profit"]["dynamic"]["max_extension_price_units"] = 10.0
        profile["take_profit"]["dynamic"]["emergency_server_tp_enabled"] = True
        profile["take_profit"]["dynamic"]["emergency_server_tp_price_units"] = 8.0
        bt = engine(profile)
        original, hard = bt._initial_targets("BUY", 100.0, 2.0)
        self.assertEqual(103.0, original)
        self.assertEqual(108.0, hard)


class DynamicManagementTests(unittest.TestCase):
    def dynamic_profile(self) -> dict:
        profile = make_profile()
        profile["take_profit"]["mode"] = "ZRSI_DYNAMIC"
        profile["take_profit"]["fixed_price_units"] = 3.0
        profile["take_profit"]["dynamic"]["extend_use_z"] = True
        profile["take_profit"]["dynamic"]["extend_use_rsi"] = True
        profile["take_profit"]["dynamic"]["extend_logic"] = "BOTH"
        profile["take_profit"]["dynamic"]["exit_z_reverse_delta"] = 0.5
        profile["take_profit"]["dynamic"]["exit_rsi_reverse_delta"] = 4.0
        return profile

    def test_extension_strength_compares_to_signal_baseline(self):
        bt = engine(self.dynamic_profile())
        position = open_position()
        self.assertTrue(bt._continuation_strong(position, 50.0, 0.0))
        self.assertFalse(bt._continuation_strong(position, 44.0, 0.0))
        self.assertFalse(bt._continuation_strong(position, 50.0, -0.6))

    def test_dynamic_reversal_uses_configured_deltas(self):
        bt = engine(self.dynamic_profile())
        position = open_position()
        position.dynamic_peak_rsi = 60.0
        position.dynamic_peak_z = 1.0
        self.assertTrue(bt._dynamic_reversal(position, 55.0, 0.4))

    def test_dynamic_time_cap_exits_on_next_bar_open(self):
        profile = self.dynamic_profile()
        profile["take_profit"]["dynamic"]["max_extension_minutes"] = 1
        bt = engine(profile)
        state = BacktestState(balance=10_000, peak_equity=10_000)
        position = open_position(hard_tp=120.0)
        position.dynamic_extended = True
        position.dynamic_extension_time = 1_704_067_200
        state.positions.append(position)
        bar = Bar(1_704_067_260, 101.0, 101.5, 100.5, 101.2, 1)
        bt._process_positions(state, dataset([bar]), bar, 0.0)
        self.assertEqual([], state.positions)
        self.assertEqual("DYNAMIC_MAX_TIME", state.trades[0]["exit_reason"])
        self.assertEqual(101.0, state.trades[0]["exit_price"])

    def test_dynamic_original_tp_lock_only_tightens(self):
        profile = self.dynamic_profile()
        profile["take_profit"]["dynamic"]["extend_use_z"] = False
        profile["take_profit"]["dynamic"]["extend_use_rsi"] = True
        profile["take_profit"]["dynamic"]["lock_sl_at_original_tp"] = True
        profile["take_profit"]["dynamic"]["lock_profit_buffer"] = 0.0
        bt = engine(profile)
        strategy = StrategyEngine(profile)
        strategy.history["M1"] = [
            Bar(1_704_067_200, 100, 101, 99, 100, 1),
            Bar(1_704_067_260, 100, 104, 100, 104, 1),
        ]
        state = BacktestState(balance=10_000, peak_equity=10_000)
        position = open_position(sl=98.0, original_tp=103.0, hard_tp=110.0)
        position.dynamic_extended = True
        position.dynamic_extension_time = 1_704_067_260
        position.mfe_price_units = 4.0
        state.positions.append(position)
        bar = strategy.history["M1"][-1]

        bt._observe_position_management(
            state,
            strategy,
            dataset(strategy.history["M1"]),
            bar,
            0.0,
        )
        self.assertEqual(103.0, position.sl)
        self.assertTrue(position.dynamic_lock_applied)

        # A later lower candidate can never widen the locked BUY stop.
        self.assertFalse(bt._apply_stop_candidate(
            position,
            102.0,
            minimum_step=0.0,
        ))
        self.assertEqual(103.0, position.sl)


class PartialAndTrailingTests(unittest.TestCase):
    def test_partial_close_realizes_once_and_final_trade_aggregates_pnl(self):
        profile = make_profile()
        profile["management"]["partial_close_enabled"] = True
        profile["management"]["partial_close_percent"] = 50.0
        bt = engine(profile, commission=2.0)
        ds = dataset()
        state = BacktestState(balance=10_000, peak_equity=10_000)
        position = open_position(volume=0.10)
        state.positions.append(position)
        bar = Bar(1_704_067_320, 102.0, 102.5, 101.5, 102.0, 1)

        bt._apply_partial_close(state, ds, position, bar, 0.0)
        self.assertTrue(position.partial_close_applied)
        self.assertEqual(0.05, position.volume)
        self.assertEqual(0.05, position.partial_close_event["volume"])
        balance_after_partial = state.balance
        bt._close_position(
            state,
            ds,
            position,
            exit_time=bar.time + 60,
            exit_price=103.0,
            reason="TEST_FINAL",
        )
        trade = state.trades[0]
        self.assertGreater(balance_after_partial, 10_000)
        self.assertEqual(0.10, trade["volume"])
        self.assertEqual(0.05, trade["final_close_volume"])
        self.assertTrue(trade["partial_close_applied"])
        self.assertAlmostEqual(
            10_000 + trade["net_pl"],
            state.balance,
            places=8,
        )

    def test_stop_candidate_can_only_improve_and_respects_step(self):
        bt = engine()
        buy = open_position(sl=98.0)
        self.assertFalse(bt._apply_stop_candidate(
            buy, 97.5, minimum_step=0.0
        ))
        self.assertFalse(bt._apply_stop_candidate(
            buy, 98.1, minimum_step=0.2
        ))
        self.assertTrue(bt._apply_stop_candidate(
            buy, 98.2, minimum_step=0.2
        ))
        self.assertEqual(98.2, buy.sl)

        sell = open_position(
            side="SELL",
            entry=100.0,
            sl=102.0,
            original_tp=97.0,
            hard_tp=90.0,
        )
        self.assertFalse(bt._apply_stop_candidate(
            sell, 102.5, minimum_step=0.0
        ))
        self.assertTrue(bt._apply_stop_candidate(
            sell, 101.5, minimum_step=0.2
        ))
        self.assertEqual(101.5, sell.sl)

    def test_structure_and_atr_trailing_candidates_use_closed_history(self):
        profile = make_profile()
        profile["stop_loss"]["structure_timeframe"] = "M1"
        profile["stop_loss"]["structure_buffer_price_units"] = 0.2
        profile["stop_loss"]["atr_timeframe"] = "M1"
        profile["stop_loss"]["atr_period"] = 2
        profile["management"]["trailing_enabled"] = True
        profile["management"]["trailing_structure_lookback"] = 2
        bt = engine(profile)
        strategy = StrategyEngine(profile)
        strategy.history["M1"] = [
            Bar(60, 100, 101, 99, 100, 1),
            Bar(120, 100, 102, 100, 101, 1),
            Bar(180, 101, 103, 101, 102, 1),
        ]
        position = open_position()
        profile["management"]["trailing_mode"] = "STRUCTURE"
        bt = engine(profile)
        structure = bt._trailing_candidate(
            strategy, position, 102.0, 0.0
        )
        self.assertAlmostEqual(99.8, structure)

        profile["management"]["trailing_mode"] = "ATR"
        profile["management"]["trailing_atr_multiplier"] = 1.0
        bt = engine(profile)
        atr_candidate = bt._trailing_candidate(
            strategy, position, 104.0, 0.0
        )
        self.assertIsNotNone(atr_candidate)
        self.assertLess(atr_candidate, 104.0)


class OptimizerParityTests(unittest.TestCase):
    def test_stop_confirm_parameters_are_optimizable_when_active(self):
        profile = make_profile()
        profile["entry"]["mode"] = "STOP_CONFIRM"
        ranges = parse_parameter_ranges(
            [
                {
                    "path": "entry.pending_buffer_price_units",
                    "min": 0.0,
                    "max": 0.2,
                    "step": 0.1,
                },
                {
                    "path": "entry.pending_expiration_minutes",
                    "min": 2,
                    "max": 4,
                    "step": 1,
                },
            ],
            profile,
        )
        self.assertEqual(
            {
                "entry.pending_buffer_price_units",
                "entry.pending_expiration_minutes",
            },
            {item.path for item in ranges},
        )

    def test_atr_parameters_are_optimizable_for_initial_or_trailing_atr(self):
        profile = make_profile()
        profile["stop_loss"]["mode"] = "ATR"
        ranges = parse_parameter_ranges(
            [
                {
                    "path": "stop_loss.atr_multiplier",
                    "min": 1.0,
                    "max": 2.0,
                    "step": 0.5,
                }
            ],
            profile,
        )
        self.assertEqual("stop_loss.atr_multiplier", ranges[0].path)

        profile = make_profile()
        profile["management"]["trailing_enabled"] = True
        profile["management"]["trailing_mode"] = "ATR"
        ranges = parse_parameter_ranges(
            [
                {
                    "path": "management.trailing_atr_multiplier",
                    "min": 0.5,
                    "max": 1.5,
                    "step": 0.5,
                },
                {
                    "path": "stop_loss.atr_period",
                    "min": 7,
                    "max": 14,
                    "step": 7,
                },
            ],
            profile,
        )
        self.assertEqual(2, len(ranges))

    def test_dynamic_tp_parameters_and_indicator_periods_are_optimizable(self):
        profile = make_profile()
        profile["take_profit"]["mode"] = "ZRSI_DYNAMIC"
        profile["trigger"]["rsi_enabled"] = False
        profile["trigger"]["z_enabled"] = False
        profile["take_profit"]["dynamic"]["extend_use_rsi"] = True
        profile["take_profit"]["dynamic"]["extend_use_z"] = True

        ranges = parse_parameter_ranges(
            [
                {
                    "path": "trigger.rsi_period",
                    "min": 7,
                    "max": 14,
                    "step": 7,
                },
                {
                    "path": "trigger.z_period",
                    "min": 10,
                    "max": 20,
                    "step": 10,
                },
                {
                    "path": "take_profit.fixed_price_units",
                    "min": 2.0,
                    "max": 4.0,
                    "step": 1.0,
                },
                {
                    "path": "take_profit.dynamic.max_extension_price_units",
                    "min": 2.0,
                    "max": 6.0,
                    "step": 2.0,
                },
            ],
            profile,
        )
        self.assertEqual(4, len(ranges))

    def test_inactive_dynamic_parameter_is_rejected(self):
        profile = make_profile()
        with self.assertRaises(OptimizerError):
            parse_parameter_ranges(
                [
                    {
                        "path": "take_profit.dynamic.max_extension_minutes",
                        "min": 5,
                        "max": 10,
                        "step": 5,
                    }
                ],
                profile,
            )



class DeterminismTests(unittest.TestCase):
    def test_task013_profile_repeat_is_hash_deterministic(self):
        # Reuse a short strategy-replay fixture that can complete without
        # requiring the dynamic extension to fire. The important assertion is
        # that enabling the Task 013 code path does not introduce nondeterminism.
        start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
        closes = [100.0, 99.0, 98.0, 97.0, 100.0, 102.0, 101.0, 102.0]
        bars: list[Bar] = []
        previous = closes[0]
        for index, close in enumerate(closes):
            open_price = previous if index else close
            bars.append(
                Bar(
                    start + index * 60,
                    open_price,
                    max(open_price, close) + 0.2,
                    min(open_price, close) - 0.2,
                    close,
                    100 + index,
                )
            )
            previous = close

        profile = make_profile()
        profile["strategy"]["allow_sell"] = False
        profile["trigger"]["rsi_enabled"] = True
        profile["trigger"]["rsi_period"] = 2
        profile["trigger"]["rsi_reversal_delta"] = 10.0
        profile["take_profit"]["mode"] = "ZRSI_DYNAMIC"
        profile["take_profit"]["dynamic"]["extend_use_z"] = False
        profile["take_profit"]["dynamic"]["extend_use_rsi"] = True
        profile["take_profit"]["dynamic"]["near_tp_distance"] = 0.5
        ds = dataset(bars)

        first = engine(profile).run(
            ds, from_date="2024-01-01", to_date="2024-01-01"
        )
        second = engine(profile).run(
            ds, from_date="2024-01-01", to_date="2024-01-01"
        )
        self.assertEqual(first["result_hash"], second["result_hash"])
        self.assertEqual(first["trades"], second["trades"])


class TemporalAndBrokerRegressionTests(unittest.TestCase):
    def test_pending_intrabar_fill_cannot_exit_at_pre_entry_open(self):
        for side in ("BUY", "SELL"):
            with self.subTest(side=side):
                profile = make_profile()
                profile["entry"]["mode"] = "STOP_CONFIRM"
                bt = engine(profile)
                strategy = StrategyEngine(profile)
                strategy.direction = side
                start = 1_704_067_200
                signal_bar = Bar(start, 100, 102, 98, 100, 1)
                strategy.history["M1"] = [signal_bar]
                bar = Bar(start + 60, 99 if side == "BUY" else 101, 103, 97, 100, 1)
                ds = dataset([signal_bar, bar])
                state = BacktestState(balance=10_000)
                bt._try_open_signal(state, strategy, ds, bar, {
                    "sequence": 1, "side": side, "bar_time": start,
                    "detected_close_time": start + 60,
                }, 0.0)
                bt._process_pending_entries(state, strategy, ds, bar, 0.0)
                self.assertEqual(1, len(state.positions))
                protective_sl = state.positions[0].sl
                self.assertTrue(state.positions[0].entry_filled_intrabar)
                bt._process_positions(state, ds, bar, 0.0)
                self.assertEqual("SL", state.trades[0]["exit_reason"])
                self.assertAlmostEqual(protective_sl, state.trades[0]["exit_price"])
                self.assertNotEqual(bar.open, state.trades[0]["exit_price"])

    def test_pending_age_counts_trigger_timeframe_bars(self):
        profile = make_profile()
        profile["timeframes"]["trigger"] = "M5"
        profile["entry"]["mode"] = "STOP_CONFIRM"
        profile["entry"]["max_signal_age_bars"] = 2
        profile["entry"]["pending_expiration_minutes"] = 30
        bt = engine(profile)
        strategy = StrategyEngine(profile)
        start = 1_704_067_200
        strategy.history["M5"] = [Bar(start, 100, 101, 99, 100, 1)]
        state = BacktestState(balance=10_000)
        bar = Bar(start + 300, 100, 100.5, 99.5, 100, 1)
        bt._try_open_signal(state, strategy, dataset([bar]), bar, {
            "sequence": 1, "side": "BUY", "bar_time": start,
            "detected_close_time": start + 300,
        }, 0)
        self.assertEqual(start + 900, state.pending_entries[0].signal_stale_at)

    def test_breakeven_rejects_stop_on_wrong_side_of_close(self):
        profile = make_profile()
        profile["management"]["breakeven_enabled"] = True
        bt = engine(profile)
        for side in ("BUY", "SELL"):
            with self.subTest(side=side):
                buy = side == "BUY"
                position = open_position(side=side, sl=98 if buy else 102,
                                         original_tp=110 if buy else 90)
                state = BacktestState(balance=10_000, positions=[position])
                bar = Bar(1_704_067_320, 100, 102.5 if buy else 100.5,
                          99.5 if buy else 97.5, 100, 1)
                bt._process_positions(state, dataset([bar]), bar, 0)
                self.assertFalse(position.breakeven_applied)
                self.assertEqual(98 if buy else 102, position.sl)

    def test_partial_observed_at_close_fills_once_at_next_open(self):
        profile = make_profile()
        profile["management"]["partial_close_enabled"] = True
        bt = engine(profile, commission=2)
        strategy = StrategyEngine(profile)
        first = Bar(1_704_067_320, 100, 102.5, 99.5, 102, 1)
        second = Bar(first.time + 60, 101, 102, 100.5, 101.5, 1)
        ds = dataset([first, second])
        position = open_position(original_tp=110)
        state = BacktestState(balance=10_000, positions=[position])
        bt._process_positions(state, ds, first, 0)
        strategy.history["M1"] = [first]
        bt._observe_position_management(state, strategy, ds, first, 0)
        self.assertTrue(position.partial_close_pending)
        self.assertFalse(position.partial_close_applied)
        self.assertEqual(10_000, state.balance)
        bt._process_positions(state, ds, second, 0)
        self.assertEqual(second.time, position.partial_close_event["time"])
        self.assertEqual(second.open, position.partial_close_event["price"])
        self.assertEqual(0.05, position.volume)
        balance = state.balance
        bt._apply_partial_close(state, ds, position, second, 0)
        self.assertEqual(balance, state.balance)
        self.assertEqual(0.05, position.volume)

    def test_gap_sl_wins_over_queued_partial_and_ignores_future_extrema(self):
        bt = engine()
        position = open_position()
        position.partial_close_pending = True
        state = BacktestState(balance=10_000, positions=[position])
        bar = Bar(1_704_067_320, 97, 110, 90, 101, 1)
        bt._process_positions(state, dataset([bar]), bar, 0)
        trade = state.trades[0]
        self.assertEqual("SL_GAP", trade["exit_reason"])
        self.assertEqual(bar.time, trade["exit_time"])
        self.assertEqual(0, trade["mfe_price_units"])
        self.assertEqual(3, trade["mae_price_units"])
        self.assertFalse(trade["partial_close_applied"])

    def test_either_uses_available_indicator_but_both_requires_both(self):
        for logic, expected in (("EITHER", True), ("BOTH", False)):
            with self.subTest(logic=logic):
                profile = make_profile()
                profile["take_profit"]["mode"] = "ZRSI_DYNAMIC"
                profile["take_profit"]["dynamic"]["extend_logic"] = logic
                bt = engine(profile)
                position = open_position()
                position.signal_trigger_z = None
                self.assertEqual(expected, bt._continuation_strong(position, 60, None))
                position.dynamic_peak_rsi = 65
                self.assertEqual(expected, bt._dynamic_reversal(position, 55, None))

    def test_old_excursion_does_not_arm_extension_after_price_retreats(self):
        profile = make_profile()
        profile["take_profit"]["mode"] = "ZRSI_DYNAMIC"
        profile["take_profit"]["dynamic"]["extend_use_z"] = False
        bt = engine(profile)
        strategy = StrategyEngine(profile)
        strategy.history["M1"] = [
            Bar(60, 98, 98.5, 97.5, 98, 1),
            Bar(120, 98, 99.5, 97.5, 99, 1),
            Bar(180, 99, 100.5, 98.5, 100, 1),
        ]
        position = open_position()
        position.mfe_price_units = 2.9
        state = BacktestState(balance=10_000, positions=[position])
        bar = strategy.history["M1"][-1]
        bt._observe_position_management(state, strategy, dataset(), bar, 0)
        self.assertFalse(position.dynamic_extended)

    def test_stop_updates_obey_tick_stop_and_freeze_rules_for_both_sides(self):
        bt = engine()
        meta = replace(metadata(), tick_size=0.1, stops_level_points=50)
        for side in ("BUY", "SELL"):
            with self.subTest(side=side):
                buy = side == "BUY"
                position = open_position(side=side, sl=98 if buy else 102)
                self.assertTrue(bt._apply_stop_candidate(
                    position, 99.26 if buy else 100.74, minimum_step=0,
                    metadata=meta, current_exit=100, observed_at=120,
                ))
                self.assertAlmostEqual(99.2 if buy else 100.8, position.sl)
                self.assertFalse(bt._apply_stop_candidate(
                    position, 99.8 if buy else 100.2, minimum_step=0,
                    metadata=meta, current_exit=100,
                ))
                frozen = replace(meta, freeze_level_points=100)
                self.assertFalse(bt._apply_stop_candidate(
                    position, 99.4 if buy else 100.6, minimum_step=0,
                    metadata=frozen, current_exit=100,
                ))
                self.assertEqual(1, len(position.management_events))

    def test_initial_stop_broker_distance_blocks_trade_without_widening(self):
        bt = engine()
        ds = replace(dataset(), metadata=replace(metadata(), stops_level_points=300))
        state = BacktestState(balance=10_000)
        strategy = StrategyEngine(make_profile())
        bar = ds.bars[1]
        bt._try_open_signal(state, strategy, ds, bar, {
            "side": "BUY", "sequence": 1, "bar_time": ds.bars[0].time,
            "detected_close_time": bar.time,
        }, 0)
        self.assertFalse(state.positions)
        self.assertEqual(1, state.skipped_signals["BROKER_INVALID_INITIAL_SL"])

    def test_dynamic_extension_only_applies_after_observed_bar(self):
        profile = make_profile()
        profile["take_profit"]["mode"] = "ZRSI_DYNAMIC"
        profile["take_profit"]["dynamic"]["extend_use_z"] = False
        bt = engine(profile)
        strategy = StrategyEngine(profile)
        position = open_position()
        state = BacktestState(balance=10_000, positions=[position])
        bar = Bar(1_704_067_320, 100, 104, 99, 103.5, 1)
        # Even if the eventual close would show strong continuation, the TP
        # that was active before this bar must be honored first.
        bt._process_positions(state, dataset([bar]), bar, 0)
        strategy.history["M1"] = [bar]
        bt._observe_position_management(state, strategy, dataset([bar]), bar, 0)
        self.assertEqual("TP", state.trades[0]["exit_reason"])
        self.assertEqual(103, state.trades[0]["exit_price"])
        self.assertFalse(state.trades[0]["dynamic_extended"])


if __name__ == "__main__":
    unittest.main()
