from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import csv
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.backtest import (
    BACKTEST_MODEL,
    BacktestEngine,
    BacktestError,
    BacktestRepository,
    DatasetMetadata,
    HistoricalDataset,
    aggregate_timeframe,
    build_close_schedule,
    load_historical_dataset,
)
from xaupy_engine.config_schema import default_profile
from xaupy_engine.strategy_engine import Bar, StrategyEngine


def test_profile():
    profile = default_profile()
    profile["profile"]["name"] = "Task011 Test"
    profile["strategy"]["allow_buy"] = True
    profile["strategy"]["allow_sell"] = False
    profile["timeframes"] = {
        "direction": "M1",
        "pullback": "M1",
        "trigger": "M1",
    }
    profile["direction"]["ma_enabled"] = False
    profile["direction"]["open_filter_enabled"] = False
    profile["pullback"]["rsi_enabled"] = False
    profile["pullback"]["z_enabled"] = False
    profile["trigger"]["rsi_enabled"] = True
    profile["trigger"]["rsi_period"] = 2
    profile["trigger"]["rsi_reversal_delta"] = 10.0
    profile["trigger"]["z_enabled"] = False
    profile["filters"]["adx"]["enabled"] = False
    profile["filters"]["atr"]["enabled"] = False
    profile["filters"]["open"]["enabled"] = False
    profile["entry"]["mode"] = "MARKET"
    profile["risk"]["sizing_mode"] = "FIXED_LOT"
    profile["risk"]["fixed_lot"] = 0.10
    profile["risk"]["max_lot"] = 0.10
    profile["risk"]["max_open_positions"] = 1
    profile["risk"]["max_trades_per_day"] = 8
    profile["risk"]["cooldown_minutes"] = 0
    profile["risk"]["max_consecutive_losses"] = 8
    profile["risk"]["max_daily_loss_pct"] = 50.0
    profile["risk"]["stop_after_daily_target"] = False
    profile["stop_loss"]["mode"] = "FIXED"
    profile["stop_loss"]["fixed_price_units"] = 2.0
    profile["stop_loss"]["min_price_units"] = 0.5
    profile["stop_loss"]["max_price_units"] = 20.0
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


def bars_for_trigger(*, ambiguous_entry=False):
    start = 1_704_067_200  # 2024-01-01 00:00 UTC
    closes = [100.0, 99.0, 98.0, 97.0, 100.0, 100.0, 101.0, 102.0]
    bars = []
    previous = closes[0]
    for index, close in enumerate(closes):
        open_price = previous if index else close
        high = max(open_price, close) + 0.2
        low = min(open_price, close) - 0.2
        if index == 5:
            open_price = 100.0
            close = 102.0
            if ambiguous_entry:
                high = 104.0
                low = 97.0
            else:
                high = 104.0
                low = 99.0
        bars.append(
            Bar(
                time=start + index * 60,
                open=open_price,
                high=high,
                low=low,
                close=close,
                tick_volume=100 + index,
            )
        )
        previous = close
    return bars


def dataset_from_bars(bars, path_name="fixture.json"):
    return HistoricalDataset(
        path=pathlib.Path(path_name),
        fingerprint="a" * 64,
        metadata=DatasetMetadata(
            symbol="XAUUSD",
            point_size=0.01,
            tick_size=0.01,
            tick_value=1.0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            timezone_offset_minutes=0,
        ),
        bars=tuple(bars),
    )


def write_json_dataset(path: pathlib.Path, bars):
    payload = {
        "schema_version": 1,
        "symbol": "XAUUSD",
        "timeframe": "M1",
        "point_size": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "timezone_offset_minutes": 0,
        "bars": [
            {
                "time": bar.time,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "tick_volume": bar.tick_volume,
            }
            for bar in bars
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class DatasetTests(unittest.TestCase):
    def test_json_dataset_inspection_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp, "data.json")
            write_json_dataset(path, bars_for_trigger())
            dataset = load_historical_dataset(path)
            info = dataset.inspect_payload()

            self.assertEqual("XAUUSD", dataset.metadata.symbol)
            self.assertEqual(8, len(dataset.bars))
            self.assertEqual(64, len(dataset.fingerprint))
            self.assertEqual("M1", info["timeframe"])
            self.assertEqual("2024-01-01", info["first_date"])

    def test_csv_dataset_requires_stable_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp, "data.csv")
            fields = [
                "time", "open", "high", "low", "close", "tick_volume",
                "symbol", "point_size", "tick_size", "tick_value",
                "volume_min", "volume_max", "volume_step",
                "timezone_offset_minutes",
            ]
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for index, bar in enumerate(bars_for_trigger()):
                    writer.writerow(
                        {
                            "time": bar.time,
                            "open": bar.open,
                            "high": bar.high,
                            "low": bar.low,
                            "close": bar.close,
                            "tick_volume": bar.tick_volume,
                            "symbol": "XAUUSD",
                            "point_size": 0.01,
                            "tick_size": 0.01,
                            "tick_value": 1.0,
                            "volume_min": 0.01,
                            "volume_max": 100.0,
                            "volume_step": 0.01,
                            "timezone_offset_minutes": 0 if index < 7 else 60,
                        }
                    )

            with self.assertRaises(BacktestError):
                load_historical_dataset(path)

    def test_out_of_order_dataset_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bars = bars_for_trigger()
            bars[3] = Bar(
                time=bars[1].time,
                open=bars[3].open,
                high=bars[3].high,
                low=bars[3].low,
                close=bars[3].close,
                tick_volume=bars[3].tick_volume,
            )
            path = pathlib.Path(tmp, "data.json")
            write_json_dataset(path, bars)
            with self.assertRaises(BacktestError):
                load_historical_dataset(path)


class AggregationTests(unittest.TestCase):
    def test_complete_m5_bucket_aggregates_exactly(self):
        start = 1_704_067_200
        bars = [
            Bar(start + i * 60, 100 + i, 101 + i, 99 + i, 100.5 + i, 10 + i)
            for i in range(5)
        ]
        result = aggregate_timeframe(bars, "M5")
        self.assertEqual(1, len(result))
        self.assertEqual(start, result[0].time)
        self.assertEqual(100, result[0].open)
        self.assertEqual(105, result[0].high)
        self.assertEqual(99, result[0].low)
        self.assertEqual(104.5, result[0].close)
        self.assertEqual(sum(10 + i for i in range(5)), result[0].tick_volume)

    def test_gapped_higher_timeframe_bucket_is_not_fabricated(self):
        start = 1_704_067_200
        bars = [
            Bar(start + i * 60, 100, 101, 99, 100, 10)
            for i in (0, 1, 3, 4)
        ]
        self.assertEqual([], aggregate_timeframe(bars, "M5"))

    def test_close_schedule_only_exposes_bar_after_close(self):
        bars = bars_for_trigger()
        schedule = build_close_schedule(bars)
        first = bars[0]
        self.assertIn(first.time + 60, schedule)
        self.assertEqual(first.time, schedule[first.time + 60]["M1"].time)


class BacktestParityTests(unittest.TestCase):
    def run_engine(self, *, ambiguous=False, profile=None, spread=0.0):
        dataset = dataset_from_bars(
            bars_for_trigger(ambiguous_entry=ambiguous)
        )
        engine = BacktestEngine(
            profile or test_profile(),
            initial_balance=10_000,
            spread_pips=spread,
            commission_per_lot=7.0,
        )
        return engine.run(
            dataset,
            from_date="2024-01-01",
            to_date="2024-01-01",
        )

    def test_backtest_detects_same_signal_as_direct_strategy_replay(self):
        bars = bars_for_trigger()
        dataset = dataset_from_bars(bars)
        profile = test_profile()
        result = BacktestEngine(
            profile,
            initial_balance=10_000,
            spread_pips=0,
            commission_per_lot=0,
        ).run(dataset, from_date="2024-01-01", to_date="2024-01-01")

        direct = StrategyEngine(profile)
        schedule = build_close_schedule(bars)
        direct_signals = []
        last_sequence = 0
        for bar in bars:
            status = direct.ingest_snapshot(
                {
                    "symbol": "XAUUSD",
                    "bars": {
                        tf: {
                            "time": item.time,
                            "open": item.open,
                            "high": item.high,
                            "low": item.low,
                            "close": item.close,
                            "tick_volume": item.tick_volume,
                        }
                        for tf, item in schedule[bar.time + 60].items()
                    },
                }
            )
            if status["signal_sequence"] > last_sequence:
                direct_signals.append(deepcopy(status["last_signal"]))
                last_sequence = status["signal_sequence"]

        self.assertEqual(1, len(direct_signals))
        self.assertGreaterEqual(len(result["trades"]), 1)
        self.assertEqual(
            direct_signals[0]["sequence"],
            result["trades"][0]["signal_sequence"],
        )
        self.assertEqual(
            direct_signals[0]["bar_time"],
            result["trades"][0]["signal_time"],
        )

    def test_market_entry_occurs_on_next_m1_bar_not_signal_bar(self):
        result = self.run_engine()
        trade = result["trades"][0]
        self.assertEqual(trade["signal_time"] + 60, trade["entry_time"])

    def test_same_bar_sl_tp_ambiguity_is_conservative_sl_first(self):
        result = self.run_engine(ambiguous=True)
        trade = result["trades"][0]
        self.assertEqual("SL_AMBIGUOUS", trade["exit_reason"])
        self.assertLess(trade["net_pl"], 0)

    def test_deterministic_repeat_has_same_hash_trades_and_curves(self):
        first = self.run_engine()
        second = self.run_engine()

        self.assertEqual(BACKTEST_MODEL, first["model"])
        self.assertEqual(first["result_hash"], second["result_hash"])
        self.assertEqual(first["trades"], second["trades"])
        self.assertEqual(first["equity_curve"], second["equity_curve"])
        self.assertEqual(first["drawdown_curve"], second["drawdown_curve"])

    def test_trade_contains_real_mae_mfe_and_metrics(self):
        result = self.run_engine()
        trade = result["trades"][0]
        self.assertGreaterEqual(trade["mfe_price_units"], 0)
        self.assertGreaterEqual(trade["mae_price_units"], 0)
        self.assertIn("mae_usd", trade)
        self.assertIn("mfe_usd", trade)
        self.assertEqual(result["metrics"]["total_trades"], len(result["trades"]))
        self.assertEqual(
            result["metrics"]["final_balance"],
            round(10_000 + result["metrics"]["net_profit"], 8),
        )

    def test_spread_and_commission_reduce_profit(self):
        clean = BacktestEngine(
            test_profile(),
            initial_balance=10_000,
            spread_pips=0,
            commission_per_lot=0,
        ).run(
            dataset_from_bars(bars_for_trigger()),
            from_date="2024-01-01",
            to_date="2024-01-01",
        )
        costly = self.run_engine(spread=20)
        self.assertLess(
            costly["metrics"]["net_profit"],
            clean["metrics"]["net_profit"],
        )

    def test_unsupported_future_execution_modes_are_rejected(self):
        for mutate in (
            lambda p: p["entry"].__setitem__("mode", "STOP_CONFIRM"),
            lambda p: p["stop_loss"].__setitem__("mode", "ATR"),
            lambda p: p["take_profit"].__setitem__("mode", "ZRSI_DYNAMIC"),
            lambda p: p["management"].__setitem__("partial_close_enabled", True),
            lambda p: p["management"].__setitem__("trailing_enabled", True),
            lambda p: p["news"].__setitem__("enabled", True),
        ):
            profile = test_profile()
            mutate(profile)
            with self.subTest(profile=profile):
                with self.assertRaises(BacktestError):
                    BacktestEngine(
                        profile,
                        initial_balance=10_000,
                        spread_pips=20,
                        commission_per_lot=7,
                    )


class RiskAndStructureTests(unittest.TestCase):
    def test_risk_percent_sizing_uses_tick_metadata_and_step(self):
        profile = test_profile()
        profile["risk"]["sizing_mode"] = "RISK_PERCENT"
        profile["risk"]["risk_percent"] = 1.0
        profile["risk"]["max_lot"] = 10.0
        engine = BacktestEngine(
            profile,
            initial_balance=10_000,
            spread_pips=0,
            commission_per_lot=0,
        )
        metadata = dataset_from_bars(bars_for_trigger()).metadata
        volume = engine._position_volume(10_000, metadata, 2.0)
        # $2 / 0.01 * $1 = $200 risk per lot; $100 risk => 0.50 lot.
        self.assertAlmostEqual(0.50, volume)

    def test_structure_stop_uses_only_already_closed_history(self):
        profile = test_profile()
        profile["stop_loss"]["mode"] = "STRUCTURE"
        profile["stop_loss"]["structure_timeframe"] = "M1"
        profile["stop_loss"]["structure_lookback"] = 3
        profile["stop_loss"]["structure_buffer_price_units"] = 0.5
        profile["stop_loss"]["min_price_units"] = 0.5
        profile["stop_loss"]["max_price_units"] = 20.0

        engine = BacktestEngine(
            profile,
            initial_balance=10_000,
            spread_pips=0,
            commission_per_lot=0,
        )
        strategy = StrategyEngine(profile)
        strategy.history["M1"] = [
            Bar(60, 100, 101, 98, 100, 1),
            Bar(120, 100, 102, 97, 101, 1),
            Bar(180, 101, 103, 99, 102, 1),
        ]
        dataset = dataset_from_bars(bars_for_trigger())
        sl, distance = engine._initial_stop(
            strategy,
            dataset,
            "BUY",
            101.0,
            0.0,
        )
        self.assertEqual(96.5, sl)
        self.assertEqual(4.5, distance)

    def test_session_filter_uses_dataset_broker_offset(self):
        profile = test_profile()
        profile["sessions"]["timezone"] = "BROKER"
        profile["sessions"]["session1_enabled"] = True
        profile["sessions"]["session1_start"] = "07:00"
        profile["sessions"]["session1_end"] = "08:00"

        engine = BacktestEngine(
            profile,
            initial_balance=10_000,
            spread_pips=0,
            commission_per_lot=0,
        )
        dataset = HistoricalDataset(
            path=pathlib.Path("x.json"),
            fingerprint="b" * 64,
            metadata=DatasetMetadata(
                symbol="XAUUSD",
                point_size=0.01,
                tick_size=0.01,
                tick_value=1.0,
                volume_min=0.01,
                volume_max=10,
                volume_step=0.01,
                timezone_offset_minutes=120,
            ),
            bars=tuple(bars_for_trigger()),
        )
        utc_0500 = int(datetime(2024, 1, 1, 5, 0, tzinfo=timezone.utc).timestamp())
        utc_0700 = int(datetime(2024, 1, 1, 7, 0, tzinfo=timezone.utc).timestamp())
        self.assertTrue(engine._session_allowed(dataset, utc_0500))
        self.assertFalse(engine._session_allowed(dataset, utc_0700))


class RepositoryTests(unittest.TestCase):
    def test_save_history_get_delete(self):
        result = BacktestEngine(
            test_profile(),
            initial_balance=10_000,
            spread_pips=0,
            commission_per_lot=0,
        ).run(
            dataset_from_bars(bars_for_trigger()),
            from_date="2024-01-01",
            to_date="2024-01-01",
        )

        with tempfile.TemporaryDirectory() as tmp:
            repo = BacktestRepository(tmp)
            stored = repo.save(result)
            history = repo.history()

            self.assertEqual(1, len(history))
            self.assertEqual(stored["run_id"], history[0]["run_id"])
            loaded = repo.get(stored["run_id"])
            self.assertEqual(result["result_hash"], loaded["result_hash"])
            self.assertTrue(repo.delete(stored["run_id"]))
            self.assertEqual([], repo.history())
            self.assertFalse(repo.delete(stored["run_id"]))


if __name__ == "__main__":
    unittest.main()
