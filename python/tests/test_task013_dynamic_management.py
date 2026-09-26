from __future__ import annotations

from datetime import datetime, timezone
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
        profile["take_profit"]["dynamic"]["extend_use_rsi"] = False
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


if __name__ == "__main__":
    unittest.main()
