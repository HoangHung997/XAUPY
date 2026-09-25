from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.backtest import DatasetMetadata, HistoricalDataset
from xaupy_engine.config_schema import default_profile
from xaupy_engine.optimizer import (
    MAX_COMBINATIONS,
    OBJECTIVE_ID,
    OptimizerEngine,
    OptimizerError,
    OptimizerJobManager,
    OptimizerRepository,
    ParameterRange,
    apply_parameters,
    build_walk_forward_plan,
    combination_count,
    heatmap_from_result,
    parameter_combinations,
    parse_parameter_ranges,
    robust_score,
    walk_forward_aggregate,
)
from xaupy_engine.strategy_engine import Bar


def optimizer_profile():
    profile = default_profile()
    profile["profile"]["name"] = "Task012 Test"
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
    profile["risk"]["max_lot"] = 1.0
    profile["risk"]["max_open_positions"] = 1
    profile["risk"]["max_trades_per_day"] = 20
    profile["risk"]["cooldown_minutes"] = 0
    profile["risk"]["max_consecutive_losses"] = 20
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
    for day in (
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday"
    ):
        profile["sessions"][day] = True
    profile["news"]["enabled"] = False
    return profile


def trigger_day(start: int):
    closes = [100.0, 99.0, 98.0, 97.0, 100.0, 102.0, 101.0, 102.0]
    bars = []
    previous = closes[0]
    for index, close in enumerate(closes):
        open_price = previous if index else close
        high = max(open_price, close) + 0.2
        low = min(open_price, close) - 0.2
        if index == 5:
            open_price = 100.0
            high = 104.0
            low = 99.0
            close = 102.0
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


def multi_day_dataset(days=12):
    start = 1_704_067_200  # 2024-01-01 UTC
    bars = []
    for day in range(days):
        bars.extend(trigger_day(start + day * 86400))
    return HistoricalDataset(
        path=pathlib.Path("optimizer-fixture.json"),
        fingerprint="d" * 64,
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


def write_dataset(path: pathlib.Path, days=12):
    dataset = multi_day_dataset(days)
    payload = {
        "schema_version": 1,
        "symbol": dataset.metadata.symbol,
        "timeframe": "M1",
        **{
            key: value
            for key, value in dataset.metadata.public().items()
            if key != "symbol"
        },
        "bars": [
            {
                "time": bar.time,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "tick_volume": bar.tick_volume,
            }
            for bar in dataset.bars
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class RangeValidationTests(unittest.TestCase):
    def test_ranges_are_canonical_sorted_and_decimal_safe(self):
        profile = optimizer_profile()
        ranges = parse_parameter_ranges(
            [
                {
                    "path": "risk.fixed_lot",
                    "min": 0.05,
                    "max": 0.15,
                    "step": 0.05,
                },
                {
                    "path": "timeframes.trigger",
                    "values": ["M1", "M3"],
                },
            ],
            profile,
        )

        self.assertEqual(
            ["risk.fixed_lot", "timeframes.trigger"],
            [item.path for item in ranges],
        )
        self.assertEqual((0.05, 0.1, 0.15), ranges[0].values)
        self.assertEqual(("M1", "M3"), ranges[1].values)
        self.assertEqual(6, combination_count(ranges))

        combos = parameter_combinations(ranges)
        self.assertEqual(
            {
                "risk.fixed_lot": 0.05,
                "timeframes.trigger": "M1",
            },
            combos[0],
        )

    def test_inactive_and_locked_or_unknown_parameters_are_rejected(self):
        profile = optimizer_profile()
        with self.assertRaises(OptimizerError):
            parse_parameter_ranges(
                [{"path": "direction.ma_period", "min": 20, "max": 50, "step": 10}],
                profile,
            )
        with self.assertRaises(OptimizerError):
            parse_parameter_ranges(
                [{"path": "execution.max_retry_count", "min": 0, "max": 0, "step": 1}],
                profile,
            )
        with self.assertRaises(OptimizerError):
            parse_parameter_ranges(
                [{"path": "unknown.path", "min": 1, "max": 2, "step": 1}],
                profile,
            )

    def test_combination_limit_is_enforced(self):
        profile = optimizer_profile()
        profile["direction"]["ma_enabled"] = True
        profile["pullback"]["rsi_enabled"] = True
        with self.assertRaises(OptimizerError) as ctx:
            parse_parameter_ranges(
                [
                    {
                        "path": "direction.ma_period",
                        "min": 1,
                        "max": 1000,
                        "step": 1,
                    },
                    {
                        "path": "pullback.rsi_buy_level",
                        "min": 0,
                        "max": 100,
                        "step": 1,
                    },
                ],
                profile,
            )
        self.assertIn(f"{MAX_COMBINATIONS:,}", str(ctx.exception))

    def test_apply_parameters_uses_canonical_validation(self):
        profile = optimizer_profile()
        changed = apply_parameters(
            profile,
            {
                "risk.fixed_lot": 0.2,
                "timeframes.trigger": "M3",
            },
        )
        self.assertEqual(0.2, changed["risk"]["fixed_lot"])
        self.assertEqual("M3", changed["timeframes"]["trigger"])


class ScoreAndSweepTests(unittest.TestCase):
    def test_min_trade_count_controls_eligibility(self):
        result = {
            "metrics": {
                "total_trades": 3,
                "net_profit_pct": 5.0,
                "max_drawdown_pct": 1.0,
                "win_rate": 75.0,
                "profit_factor": 2.0,
                "gross_profit": 100.0,
                "gross_loss": -50.0,
            },
            "trades": [
                {"net_pl": 10.0},
                {"net_pl": 20.0},
                {"net_pl": -5.0},
            ],
        }
        eligible, score, sharpe = robust_score(result, min_trades=4)
        self.assertFalse(eligible)
        self.assertIsNone(score)
        self.assertIsInstance(sharpe, float)

        eligible2, score2, _ = robust_score(result, min_trades=3)
        self.assertTrue(eligible2)
        self.assertIsInstance(score2, float)

    def test_worker_count_does_not_change_hash_or_ranking(self):
        dataset = multi_day_dataset(2)
        profile = optimizer_profile()
        ranges = parse_parameter_ranges(
            [
                {
                    "path": "risk.fixed_lot",
                    "min": 0.05,
                    "max": 0.15,
                    "step": 0.05,
                },
                {
                    "path": "risk.cooldown_minutes",
                    "min": 0,
                    "max": 1,
                    "step": 1,
                },
            ],
            profile,
        )

        one = OptimizerEngine(
            profile,
            initial_balance=10000,
            spread_pips=0,
            commission_per_lot=0,
            min_trades=1,
            max_workers=1,
        ).run_sweep(
            dataset,
            from_date="2024-01-01",
            to_date="2024-01-02",
            parameter_ranges=ranges,
        )
        many = OptimizerEngine(
            profile,
            initial_balance=10000,
            spread_pips=0,
            commission_per_lot=0,
            min_trades=1,
            max_workers=4,
        ).run_sweep(
            dataset,
            from_date="2024-01-01",
            to_date="2024-01-02",
            parameter_ranges=ranges,
        )

        self.assertEqual(OBJECTIVE_ID, one["objective"])
        self.assertEqual(one["optimizer_hash"], many["optimizer_hash"])
        self.assertEqual(one["candidates"], many["candidates"])

    def test_tie_break_is_parameter_json_not_completion_order(self):
        profile = optimizer_profile()
        dataset = multi_day_dataset(1)
        ranges = parse_parameter_ranges(
            [
                {
                    "path": "risk.cooldown_minutes",
                    "min": 0,
                    "max": 2,
                    "step": 1,
                }
            ],
            profile,
        )
        result = OptimizerEngine(
            profile,
            initial_balance=10000,
            spread_pips=0,
            commission_per_lot=0,
            min_trades=1,
            max_workers=3,
        ).run_sweep(
            dataset,
            from_date="2024-01-01",
            to_date="2024-01-01",
            parameter_ranges=ranges,
        )
        eligible = [item for item in result["candidates"] if item["eligible"]]
        if len(eligible) >= 2 and eligible[0]["score"] == eligible[1]["score"]:
            self.assertLess(
                json.dumps(eligible[0]["parameters"], sort_keys=True),
                json.dumps(eligible[1]["parameters"], sort_keys=True),
            )


class HeatmapTests(unittest.TestCase):
    def test_heatmap_uses_real_candidate_average_without_interpolation(self):
        result = {
            "mode": "SWEEP",
            "parameter_ranges": [
                {"path": "a", "values": [1, 2]},
                {"path": "b", "values": [10, 20]},
            ],
            "candidates": [
                {
                    "eligible": True,
                    "parameters": {"a": 1, "b": 10},
                    "score": 2.0,
                    "trade_sharpe": 1.0,
                    "metrics": {"net_profit": 100.0},
                },
                {
                    "eligible": True,
                    "parameters": {"a": 1, "b": 10},
                    "score": 4.0,
                    "trade_sharpe": 2.0,
                    "metrics": {"net_profit": 200.0},
                },
                {
                    "eligible": True,
                    "parameters": {"a": 2, "b": 20},
                    "score": 9.0,
                    "trade_sharpe": 3.0,
                    "metrics": {"net_profit": 900.0},
                },
            ],
        }
        heatmap = heatmap_from_result(
            result,
            x_path="a",
            y_path="b",
            metric="net_profit",
        )
        cell = next(
            item
            for item in heatmap["cells"]
            if item["x"] == 1 and item["y"] == 10
        )
        missing = next(
            item
            for item in heatmap["cells"]
            if item["x"] == 1 and item["y"] == 20
        )
        self.assertEqual(150.0, cell["value"])
        self.assertEqual(2, cell["samples"])
        self.assertIsNone(missing["value"])
        self.assertEqual(0, missing["samples"])


class WalkForwardTests(unittest.TestCase):
    def test_plan_has_strict_non_overlap_and_full_out_of_sample_partition(self):
        dataset = multi_day_dataset(12)
        plan = build_walk_forward_plan(
            dataset,
            from_date="2024-01-01",
            to_date="2024-01-12",
            folds=3,
            train_ratio=0.75,
            rolling=True,
        )
        self.assertEqual(3, len(plan))
        for fold in plan:
            self.assertLess(fold["train_to"], fold["test_from"])
        self.assertEqual("2024-01-10", plan[0]["test_from"])
        self.assertEqual("2024-01-12", plan[-1]["test_to"])

    def test_rolling_and_anchored_train_start_differ_after_first_fold(self):
        dataset = multi_day_dataset(12)
        rolling = build_walk_forward_plan(
            dataset,
            from_date="2024-01-01",
            to_date="2024-01-12",
            folds=3,
            train_ratio=0.75,
            rolling=True,
        )
        anchored = build_walk_forward_plan(
            dataset,
            from_date="2024-01-01",
            to_date="2024-01-12",
            folds=3,
            train_ratio=0.75,
            rolling=False,
        )
        self.assertEqual("2024-01-01", rolling[0]["train_from"])
        self.assertEqual("2024-01-01", anchored[0]["train_from"])
        self.assertNotEqual(
            rolling[1]["train_from"],
            anchored[1]["train_from"],
        )
        self.assertEqual("2024-01-01", anchored[1]["train_from"])

    def test_walk_forward_selection_is_train_only_even_when_test_prefers_other_param(self):
        dataset = multi_day_dataset(12)
        profile = optimizer_profile()
        ranges = parse_parameter_ranges(
            [
                {
                    "path": "risk.fixed_lot",
                    "min": 0.05,
                    "max": 0.10,
                    "step": 0.05,
                }
            ],
            profile,
        )
        engine = OptimizerEngine(
            profile,
            initial_balance=10000,
            spread_pips=0,
            commission_per_lot=0,
            min_trades=1,
            max_workers=1,
        )

        class FakeBacktest:
            def __init__(self, candidate_profile, **kwargs):
                self.profile = candidate_profile

            def run(self, dataset, *, from_date, to_date):
                lot = float(self.profile["risk"]["fixed_lot"])
                # Train ranges end before the final OOS block. Train deliberately
                # prefers 0.05; test deliberately rewards 0.10 much more.
                is_test = from_date >= "2024-01-10"
                pnl = (
                    1000.0 if (is_test and lot == 0.10)
                    else 100.0 if (is_test and lot == 0.05)
                    else 200.0 if lot == 0.05
                    else 10.0
                )
                trade = {"net_pl": pnl}
                metrics = {
                    "net_profit": pnl,
                    "net_profit_pct": pnl / 100.0,
                    "gross_profit": max(0.0, pnl),
                    "gross_loss": min(0.0, pnl),
                    "profit_factor": 2.0,
                    "total_trades": 2,
                    "wins": 2,
                    "losses": 0,
                    "win_rate": 100.0,
                    "average_trade": pnl / 2.0,
                    "max_drawdown_usd": 1.0,
                    "max_drawdown_pct": 0.01,
                    "initial_balance": 10000.0,
                    "final_balance": 10000.0 + pnl,
                    "final_equity": 10000.0 + pnl,
                }
                return {
                    "metrics": metrics,
                    "trades": [trade, trade],
                    "result_hash": f"{from_date}:{to_date}:{lot}",
                }

        with patch("xaupy_engine.optimizer.BacktestEngine", FakeBacktest):
            result = engine.walk_forward(
                dataset,
                from_date="2024-01-01",
                to_date="2024-01-12",
                parameter_ranges=ranges,
                folds=3,
                train_ratio=0.75,
                rolling=False,
            )

        self.assertTrue(result["leakage_guard_passed"])
        for fold in result["folds"]:
            self.assertEqual("TRAIN_ONLY", fold["selection_source"])
            self.assertEqual(0.05, fold["best_parameters"]["risk.fixed_lot"])

    def test_walk_forward_aggregate_stability_is_bounded(self):
        folds = [
            {
                "test_trade_sharpe": 1.0,
                "test_metrics": {
                    "net_profit": 100.0,
                    "net_profit_pct": 1.0,
                    "win_rate": 60.0,
                    "max_drawdown_pct": 2.0,
                    "profit_factor": 1.5,
                },
            },
            {
                "test_trade_sharpe": 0.5,
                "test_metrics": {
                    "net_profit": -20.0,
                    "net_profit_pct": -0.2,
                    "win_rate": 48.0,
                    "max_drawdown_pct": 3.0,
                    "profit_factor": 0.9,
                },
            },
        ]
        aggregate = walk_forward_aggregate(folds)
        self.assertEqual(0.5, aggregate["positive_fold_ratio"])
        self.assertGreaterEqual(aggregate["stability"], 0.0)
        self.assertLessEqual(aggregate["stability"], 1.0)


class RepositoryAndJobTests(unittest.TestCase):
    def test_repository_save_history_get_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = OptimizerRepository(tmp)
            stored = repo.save(
                {
                    "mode": "SWEEP",
                    "model": "PARAMETER_SWEEP_V1",
                    "objective": OBJECTIVE_ID,
                    "optimizer_hash": "h" * 64,
                    "base_profile_hash": "p" * 64,
                    "dataset_file_name": "data.json",
                    "dataset_fingerprint": "d" * 64,
                    "from_date": "2024-01-01",
                    "to_date": "2024-01-02",
                    "combination_count": 1,
                    "eligible_count": 1,
                    "candidates": [
                        {
                            "eligible": True,
                            "parameters": {"risk.fixed_lot": 0.1},
                            "score": 1.0,
                            "trade_sharpe": 0.5,
                            "metrics": {"net_profit": 10.0},
                        }
                    ],
                }
            )
            history = repo.history()
            self.assertEqual(stored["run_id"], history[0]["run_id"])
            self.assertEqual(
                stored["optimizer_hash"],
                repo.get(stored["run_id"])["optimizer_hash"],
            )
            self.assertTrue(repo.delete(stored["run_id"]))
            self.assertFalse(repo.delete(stored["run_id"]))

    def test_status_without_job_id_retains_latest_terminal_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            dataset_path = root / "data.json"
            write_dataset(dataset_path, days=1)
            repo = OptimizerRepository(root / "results")
            manager = OptimizerJobManager(repo)

            started = manager.start_sweep(
                {
                    "path": str(dataset_path),
                    "from_date": "2024-01-01",
                    "to_date": "2024-01-01",
                    "initial_balance": 10000,
                    "spread_pips": 0,
                    "commission_per_lot": 0,
                    "min_trades": 1,
                    "max_workers": 1,
                    "parameter_ranges": [
                        {
                            "path": "risk.fixed_lot",
                            "min": 0.10,
                            "max": 0.10,
                            "step": 0.01,
                        }
                    ],
                },
                optimizer_profile(),
            )
            job_id = started["job_id"]

            deadline = time.time() + 10
            terminal = None
            while time.time() < deadline:
                terminal = manager.status(job_id)
                if terminal["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                    break
                time.sleep(0.02)

            self.assertIsNotNone(terminal)
            self.assertEqual("COMPLETED", terminal["status"])
            latest = manager.status()
            self.assertEqual(job_id, latest["job_id"])
            self.assertEqual("COMPLETED", latest["status"])
            self.assertEqual(terminal["result_run_id"], latest["result_run_id"])

    def test_immediate_cancel_never_persists_empty_completed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            dataset_path = root / "data.json"
            write_dataset(dataset_path, days=2)
            repo = OptimizerRepository(root / "results")
            manager = OptimizerJobManager(repo)

            gate = threading.Event()
            original = OptimizerEngine.run_sweep

            def delayed_run(engine, *args, **kwargs):
                gate.wait(timeout=1)
                return original(engine, *args, **kwargs)

            with patch.object(OptimizerEngine, "run_sweep", delayed_run):
                started = manager.start_sweep(
                    {
                        "path": str(dataset_path),
                        "from_date": "2024-01-01",
                        "to_date": "2024-01-02",
                        "initial_balance": 10000,
                        "spread_pips": 0,
                        "commission_per_lot": 0,
                        "min_trades": 1,
                        "max_workers": 1,
                        "parameter_ranges": [
                            {
                                "path": "risk.fixed_lot",
                                "min": 0.01,
                                "max": 0.02,
                                "step": 0.01,
                            }
                        ],
                    },
                    optimizer_profile(),
                )
                manager.cancel(started["job_id"])
                gate.set()

                deadline = time.time() + 10
                terminal = None
                while time.time() < deadline:
                    terminal = manager.status(started["job_id"])
                    if terminal["status"] in {"CANCELLED", "FAILED", "COMPLETED"}:
                        break
                    time.sleep(0.02)

            self.assertIsNotNone(terminal)
            self.assertEqual("CANCELLED", terminal["status"])
            self.assertIsNone(terminal["result_run_id"])
            self.assertEqual([], repo.history())

    def test_job_cancel_is_cooperative_and_does_not_persist_completed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            dataset_path = root / "data.json"
            write_dataset(dataset_path, days=2)
            repo = OptimizerRepository(root / "results")
            manager = OptimizerJobManager(repo)

            original = OptimizerEngine._evaluate_candidate

            def slow(self, index, parameters, dataset, from_date, to_date):
                time.sleep(0.08)
                return original(
                    self,
                    index,
                    parameters,
                    dataset,
                    from_date,
                    to_date,
                )

            request = {
                "path": str(dataset_path),
                "from_date": "2024-01-01",
                "to_date": "2024-01-02",
                "initial_balance": 10000,
                "spread_pips": 0,
                "commission_per_lot": 0,
                "min_trades": 1,
                "max_workers": 1,
                "parameter_ranges": [
                    {
                        "path": "risk.fixed_lot",
                        "min": 0.01,
                        "max": 0.10,
                        "step": 0.01,
                    }
                ],
            }

            with patch.object(
                OptimizerEngine,
                "_evaluate_candidate",
                slow,
            ):
                started = manager.start_sweep(
                    request,
                    optimizer_profile(),
                )
                job_id = started["job_id"]
                deadline = time.time() + 5
                while time.time() < deadline:
                    status = manager.status(job_id)
                    if status["status"] == "RUNNING":
                        break
                    time.sleep(0.01)

                manager.cancel(job_id)
                deadline = time.time() + 10
                while time.time() < deadline:
                    status = manager.status(job_id)
                    if status["status"] in {"CANCELLED", "FAILED", "COMPLETED"}:
                        break
                    time.sleep(0.02)

            self.assertEqual("CANCELLED", status["status"])
            self.assertIsNone(status["result_run_id"])
            self.assertEqual([], repo.history())


if __name__ == "__main__":
    unittest.main()
