from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import statistics
import threading
import time
from typing import Any, Callable, Iterable
from uuid import UUID, uuid4

from .backtest import (
    BACKTEST_MODEL,
    BacktestEngine,
    BacktestError,
    BacktestRepository,
    HistoricalDataset,
    load_historical_dataset,
)
from .config_schema import FIELD_BY_PATH, ConfigField, normalized_profile, validate_profile
from .journal import default_journal_directory
from .strategy_engine import StrategyEngine


OPTIMIZER_SCHEMA_VERSION = 1
SWEEP_MODEL = "PARAMETER_SWEEP_V1"
WALK_FORWARD_MODEL = "WALK_FORWARD_V1"
OBJECTIVE_ID = "ROBUST_SCORE_V1"
MAX_COMBINATIONS = 50_000
MAX_WORKERS = 8

OPTIMIZABLE_PATHS = frozenset(
    {
        "timeframes.direction",
        "timeframes.pullback",
        "timeframes.trigger",
        "direction.ma_period",
        "pullback.rsi_period",
        "pullback.rsi_buy_level",
        "pullback.rsi_sell_level",
        "trigger.rsi_period",
        "trigger.rsi_reversal_delta",
        "trigger.z_period",
        "trigger.z_reversal_delta",
        "stop_loss.fixed_price_units",
        "stop_loss.structure_lookback",
        "stop_loss.structure_buffer_price_units",
        "take_profit.fixed_price_units",
        "take_profit.rr_ratio",
        "management.breakeven_trigger_rr",
        "management.breakeven_offset_price_units",
        "risk.risk_percent",
        "risk.fixed_lot",
        "risk.max_trades_per_day",
        "risk.cooldown_minutes",
        "risk.max_consecutive_losses",
    }
)

HEATMAP_METRICS = frozenset(
    {
        "score",
        "net_profit",
        "net_profit_pct",
        "win_rate",
        "profit_factor",
        "max_drawdown_pct",
        "trade_sharpe",
    }
)


class OptimizerError(ValueError):
    """Raised when an optimization request/range/result is invalid."""


class OptimizationCancelled(RuntimeError):
    """Internal cooperative cancellation signal."""


@dataclass(frozen=True)
class ParameterRange:
    path: str
    kind: str
    values: tuple[Any, ...]

    def public(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "values": list(self.values),
            "count": len(self.values),
        }


def default_optimizer_directory() -> Path:
    override = os.environ.get("XAUPY_OPTIMIZER_DIR")
    if override:
        return Path(override).expanduser()
    return default_journal_directory().parent / "optimizations"


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node = target
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _get_path(target: dict[str, Any], path: str) -> Any:
    node: Any = target
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise OptimizerError(f"config path unavailable: {path}")
        node = node[part]
    return node


def _profile_hash(profile: dict[str, Any]) -> str:
    return StrategyEngine(normalized_profile(profile)).profile_hash


def _field_relevant(path: str, profile: dict[str, Any]) -> tuple[bool, str]:
    checks: dict[str, tuple[str, Any, str]] = {
        "direction.ma_period": (
            "direction.ma_enabled",
            True,
            "Direction MA is disabled",
        ),
        "pullback.rsi_period": (
            "pullback.rsi_enabled",
            True,
            "Pullback RSI is disabled",
        ),
        "pullback.rsi_buy_level": (
            "pullback.rsi_enabled",
            True,
            "Pullback RSI is disabled",
        ),
        "pullback.rsi_sell_level": (
            "pullback.rsi_enabled",
            True,
            "Pullback RSI is disabled",
        ),
        "trigger.rsi_period": (
            "trigger.rsi_enabled",
            True,
            "Trigger RSI is disabled",
        ),
        "trigger.rsi_reversal_delta": (
            "trigger.rsi_enabled",
            True,
            "Trigger RSI is disabled",
        ),
        "trigger.z_period": (
            "trigger.z_enabled",
            True,
            "Trigger Z is disabled",
        ),
        "trigger.z_reversal_delta": (
            "trigger.z_enabled",
            True,
            "Trigger Z is disabled",
        ),
        "stop_loss.fixed_price_units": (
            "stop_loss.mode",
            "FIXED",
            "stop_loss.mode is not FIXED",
        ),
        "stop_loss.structure_lookback": (
            "stop_loss.mode",
            "STRUCTURE",
            "stop_loss.mode is not STRUCTURE",
        ),
        "stop_loss.structure_buffer_price_units": (
            "stop_loss.mode",
            "STRUCTURE",
            "stop_loss.mode is not STRUCTURE",
        ),
        "take_profit.fixed_price_units": (
            "take_profit.mode",
            "FIXED",
            "take_profit.mode is not FIXED",
        ),
        "take_profit.rr_ratio": (
            "take_profit.mode",
            "RR",
            "take_profit.mode is not RR",
        ),
        "management.breakeven_trigger_rr": (
            "management.breakeven_enabled",
            True,
            "breakeven is disabled",
        ),
        "management.breakeven_offset_price_units": (
            "management.breakeven_enabled",
            True,
            "breakeven is disabled",
        ),
        "risk.risk_percent": (
            "risk.sizing_mode",
            "RISK_PERCENT",
            "risk.sizing_mode is not RISK_PERCENT",
        ),
        "risk.fixed_lot": (
            "risk.sizing_mode",
            "FIXED_LOT",
            "risk.sizing_mode is not FIXED_LOT",
        ),
    }
    check = checks.get(path)
    if check is None:
        return True, ""
    owner_path, expected, reason = check
    return _get_path(profile, owner_path) == expected, reason


def _coerce_enum(field: ConfigField, value: Any) -> str:
    text = str(value).strip().upper()
    if text not in field.enum:
        raise OptimizerError(
            f"{field.path}: {value!r} is not one of {list(field.enum)}"
        )
    return text


def _decimal(value: Any, name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise OptimizerError(f"{name} must be numeric") from exc
    if not parsed.is_finite():
        raise OptimizerError(f"{name} must be finite")
    return parsed


def _numeric_values(
    field: ConfigField,
    minimum: Any,
    maximum: Any,
    step: Any,
) -> tuple[Any, ...]:
    lo = _decimal(minimum, f"{field.path}.min")
    hi = _decimal(maximum, f"{field.path}.max")
    inc = _decimal(step, f"{field.path}.step")
    if inc <= 0:
        raise OptimizerError(f"{field.path}.step must be positive")
    if hi < lo:
        raise OptimizerError(f"{field.path}.max must be >= min")

    if field.minimum is not None and lo < Decimal(str(field.minimum)):
        raise OptimizerError(
            f"{field.path}.min is below schema minimum {field.minimum}"
        )
    if field.maximum is not None and hi > Decimal(str(field.maximum)):
        raise OptimizerError(
            f"{field.path}.max exceeds schema maximum {field.maximum}"
        )

    values: list[Any] = []
    current = lo
    while current <= hi:
        if len(values) >= 10_000:
            raise OptimizerError(f"{field.path} expands to too many values")
        if field.kind == "int":
            if current != current.to_integral_value():
                raise OptimizerError(f"{field.path} integer range produced non-integer value")
            values.append(int(current))
        else:
            values.append(float(current))
        current += inc

    if not values:
        raise OptimizerError(f"{field.path} range is empty")
    return tuple(values)


def parse_parameter_ranges(
    raw_ranges: Any,
    base_profile: dict[str, Any],
) -> tuple[ParameterRange, ...]:
    if not isinstance(raw_ranges, list) or not raw_ranges:
        raise OptimizerError("parameter_ranges must be a non-empty array")

    profile = normalized_profile(base_profile)
    seen: set[str] = set()
    parsed: list[ParameterRange] = []

    for index, raw in enumerate(raw_ranges):
        if not isinstance(raw, dict):
            raise OptimizerError(f"parameter_ranges[{index}] must be object")

        path = str(raw.get("path", "")).strip()
        if path not in OPTIMIZABLE_PATHS:
            raise OptimizerError(f"parameter is not optimizable in Task 012: {path}")
        if path in seen:
            raise OptimizerError(f"duplicate optimizer parameter: {path}")
        seen.add(path)

        field = FIELD_BY_PATH.get(path)
        if field is None:
            raise OptimizerError(f"canonical config field not found: {path}")
        if field.locked_value is not None:
            raise OptimizerError(f"locked config field cannot be optimized: {path}")

        relevant, reason = _field_relevant(path, profile)
        if not relevant:
            raise OptimizerError(f"{path} is inactive: {reason}")

        if field.kind == "enum":
            raw_values = raw.get("values")
            if not isinstance(raw_values, list) or not raw_values:
                raise OptimizerError(f"{path}.values must be non-empty array")
            values: list[str] = []
            for value in raw_values:
                parsed_value = _coerce_enum(field, value)
                if parsed_value not in values:
                    values.append(parsed_value)
            parsed.append(ParameterRange(path, field.kind, tuple(values)))
            continue

        if field.kind not in {"int", "float"}:
            raise OptimizerError(
                f"Task 012 optimizer supports enum/int/float only: {path}"
            )

        values = _numeric_values(
            field,
            raw.get("min"),
            raw.get("max"),
            raw.get("step"),
        )
        parsed.append(ParameterRange(path, field.kind, values))

    parsed.sort(key=lambda item: item.path)
    count = combination_count(parsed)
    if count > MAX_COMBINATIONS:
        raise OptimizerError(
            f"parameter sweep expands to {count:,} combinations; "
            f"Task 012 limit is {MAX_COMBINATIONS:,}"
        )
    return tuple(parsed)


def combination_count(ranges: Iterable[ParameterRange]) -> int:
    total = 1
    found = False
    for item in ranges:
        found = True
        total *= len(item.values)
        if total > MAX_COMBINATIONS:
            return total
    return total if found else 0


def parameter_combinations(
    ranges: tuple[ParameterRange, ...],
) -> list[dict[str, Any]]:
    if not ranges:
        return []
    keys = [item.path for item in ranges]
    return [
        dict(zip(keys, values, strict=True))
        for values in itertools.product(*(item.values for item in ranges))
    ]


def apply_parameters(
    base_profile: dict[str, Any],
    parameters: dict[str, Any],
) -> dict[str, Any]:
    profile = deepcopy(normalized_profile(base_profile))
    for path in sorted(parameters):
        _set_path(profile, path, parameters[path])

    errors = validate_profile(profile)
    if errors:
        raise OptimizerError(
            "candidate config invalid: " + " | ".join(errors)
        )
    return profile


def trade_sample_sharpe(result: dict[str, Any]) -> float:
    trades = result.get("trades")
    if not isinstance(trades, list) or len(trades) < 2:
        return 0.0

    values = [
        float(item.get("net_pl", 0.0))
        for item in trades
        if isinstance(item, dict)
    ]
    if len(values) < 2:
        return 0.0

    mean = statistics.fmean(values)
    stdev = statistics.stdev(values)
    if stdev <= 1e-12:
        if mean > 0:
            return 10.0
        if mean < 0:
            return -10.0
        return 0.0

    value = mean / stdev * math.sqrt(len(values))
    return round(max(-20.0, min(20.0, value)), 8)


def robust_score(
    result: dict[str, Any],
    *,
    min_trades: int,
) -> tuple[bool, float | None, float]:
    metrics = result.get("metrics")
    if not isinstance(metrics, dict):
        raise OptimizerError("backtest result is missing metrics")

    trades = int(metrics.get("total_trades", 0))
    sharpe = trade_sample_sharpe(result)
    if trades < min_trades:
        return False, None, sharpe

    net_pct = float(metrics.get("net_profit_pct", 0.0))
    max_dd = float(metrics.get("max_drawdown_pct", 0.0))
    win_rate = float(metrics.get("win_rate", 0.0))
    raw_pf = metrics.get("profit_factor")
    if raw_pf is None:
        gross_profit = float(metrics.get("gross_profit", 0.0))
        gross_loss = float(metrics.get("gross_loss", 0.0))
        pf = 5.0 if gross_profit > 0 and abs(gross_loss) <= 1e-12 else 0.0
    else:
        pf = max(0.0, float(raw_pf))

    score = (
        net_pct
        - 1.25 * max_dd
        + 2.5 * min(pf, 5.0)
        + 0.04 * win_rate
        + 2.0 * sharpe
    )
    return True, round(score, 8), sharpe


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    score = candidate.get("score")
    numeric = float(score) if isinstance(score, (int, float)) else -1e100
    params = json.dumps(
        candidate.get("parameters", {}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (-numeric, params)


def _candidate_summary(
    index: int,
    parameters: dict[str, Any],
    result: dict[str, Any],
    min_trades: int,
) -> dict[str, Any]:
    eligible, score, sharpe = robust_score(result, min_trades=min_trades)
    return {
        "index": index,
        "parameters": dict(sorted(parameters.items())),
        "eligible": eligible,
        "score": score,
        "trade_sharpe": sharpe,
        "metrics": deepcopy(result["metrics"]),
        "result_hash": result["result_hash"],
    }


def _optimizer_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class OptimizerEngine:
    def __init__(
        self,
        base_profile: dict[str, Any],
        *,
        initial_balance: float,
        spread_pips: float,
        commission_per_lot: float,
        min_trades: int = 20,
        max_workers: int = 1,
    ) -> None:
        self.base_profile = normalized_profile(base_profile)
        self.base_profile_hash = _profile_hash(self.base_profile)
        self.initial_balance = float(initial_balance)
        self.spread_pips = float(spread_pips)
        self.commission_per_lot = float(commission_per_lot)
        self.min_trades = int(min_trades)
        self.max_workers = max(
            1,
            min(
                MAX_WORKERS,
                int(max_workers),
                os.cpu_count() or 1,
            ),
        )

        if not math.isfinite(self.initial_balance) or self.initial_balance <= 0:
            raise OptimizerError("initial_balance must be positive")
        if not math.isfinite(self.spread_pips) or self.spread_pips < 0:
            raise OptimizerError("spread_pips must be >= 0")
        if not math.isfinite(self.commission_per_lot) or self.commission_per_lot < 0:
            raise OptimizerError("commission_per_lot must be >= 0")
        if not 1 <= self.min_trades <= 100_000:
            raise OptimizerError("min_trades must be 1..100000")

        # Preflight Task 011 support before scheduling thousands of candidates.
        BacktestEngine(
            self.base_profile,
            initial_balance=self.initial_balance,
            spread_pips=self.spread_pips,
            commission_per_lot=self.commission_per_lot,
        )

    def run_sweep(
        self,
        dataset: HistoricalDataset,
        *,
        from_date: str,
        to_date: str,
        parameter_ranges: tuple[ParameterRange, ...],
        cancel_event: threading.Event | None = None,
        progress: Callable[[int, int, int], None] | None = None,
    ) -> dict[str, Any]:
        combinations = parameter_combinations(parameter_ranges)
        total = len(combinations)
        if total <= 0:
            raise OptimizerError("optimizer has no combinations")
        if total > MAX_COMBINATIONS:
            raise OptimizerError("optimizer combination limit exceeded")

        candidates: list[dict[str, Any] | None] = [None] * total
        completed = 0
        in_flight: dict[Any, int] = {}
        iterator = iter(enumerate(combinations))

        def schedule(executor: ThreadPoolExecutor) -> None:
            target = max(self.max_workers, self.max_workers * 2)
            while len(in_flight) < target:
                if cancel_event is not None and cancel_event.is_set():
                    return
                try:
                    index, parameters = next(iterator)
                except StopIteration:
                    return
                future = executor.submit(
                    self._evaluate_candidate,
                    index,
                    parameters,
                    dataset,
                    from_date,
                    to_date,
                )
                in_flight[future] = index

        with ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="xaupy-opt",
        ) as executor:
            schedule(executor)
            while in_flight:
                done, _ = wait(
                    tuple(in_flight),
                    return_when=FIRST_COMPLETED,
                )
                for future in done:
                    index = in_flight.pop(future)
                    candidates[index] = future.result()
                    completed += 1
                if progress is not None:
                    progress(completed, total, len(in_flight))

                if cancel_event is not None and cancel_event.is_set():
                    for future in in_flight:
                        future.cancel()
                    raise OptimizationCancelled("optimizer cancelled")
                schedule(executor)

        final_candidates = [
            candidate
            for candidate in candidates
            if candidate is not None
        ]
        eligible = [
            candidate
            for candidate in final_candidates
            if candidate["eligible"]
        ]
        eligible.sort(key=_candidate_sort_key)
        for rank, candidate in enumerate(eligible, start=1):
            candidate["rank"] = rank

        ineligible = [
            candidate
            for candidate in final_candidates
            if not candidate["eligible"]
        ]
        ineligible.sort(key=lambda item: int(item["index"]))
        ordered = eligible + ineligible

        deterministic = {
            "schema_version": OPTIMIZER_SCHEMA_VERSION,
            "mode": "SWEEP",
            "model": SWEEP_MODEL,
            "objective": OBJECTIVE_ID,
            "backtest_model": BACKTEST_MODEL,
            "base_profile_hash": self.base_profile_hash,
            "base_profile": deepcopy(self.base_profile),
            "dataset_file_name": dataset.path.name,
            "dataset_fingerprint": dataset.fingerprint,
            "dataset_metadata": dataset.metadata.public(),
            "from_date": str(from_date),
            "to_date": str(to_date),
            "initial_balance": self.initial_balance,
            "spread_pips": self.spread_pips,
            "commission_per_lot": self.commission_per_lot,
            "min_trades": self.min_trades,
            "parameter_ranges": [
                item.public()
                for item in parameter_ranges
            ],
            "combination_count": total,
            "evaluated_count": len(final_candidates),
            "eligible_count": len(eligible),
            "ineligible_count": len(ineligible),
            "candidates": ordered,
        }
        hash_payload = deepcopy(deterministic)
        # Worker scheduling is intentionally absent from deterministic evidence.
        deterministic["optimizer_hash"] = _optimizer_hash(hash_payload)
        deterministic["workers_used"] = self.max_workers
        return deterministic

    def _evaluate_candidate(
        self,
        index: int,
        parameters: dict[str, Any],
        dataset: HistoricalDataset,
        from_date: str,
        to_date: str,
    ) -> dict[str, Any]:
        try:
            profile = apply_parameters(self.base_profile, parameters)
            result = BacktestEngine(
                profile,
                initial_balance=self.initial_balance,
                spread_pips=self.spread_pips,
                commission_per_lot=self.commission_per_lot,
            ).run(
                dataset,
                from_date=from_date,
                to_date=to_date,
            )
            return _candidate_summary(
                index,
                parameters,
                result,
                self.min_trades,
            )
        except (BacktestError, OptimizerError, ValueError) as exc:
            return {
                "index": index,
                "parameters": dict(sorted(parameters.items())),
                "eligible": False,
                "score": None,
                "trade_sharpe": 0.0,
                "metrics": {
                    "net_profit": 0.0,
                    "net_profit_pct": 0.0,
                    "gross_profit": 0.0,
                    "gross_loss": 0.0,
                    "profit_factor": None,
                    "total_trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "win_rate": 0.0,
                    "average_trade": 0.0,
                    "max_drawdown_usd": 0.0,
                    "max_drawdown_pct": 0.0,
                    "initial_balance": self.initial_balance,
                    "final_balance": self.initial_balance,
                    "final_equity": self.initial_balance,
                },
                "result_hash": None,
                "rejection_reason": str(exc),
            }

    def walk_forward(
        self,
        dataset: HistoricalDataset,
        *,
        from_date: str,
        to_date: str,
        parameter_ranges: tuple[ParameterRange, ...],
        folds: int,
        train_ratio: float,
        rolling: bool,
        cancel_event: threading.Event | None = None,
        progress: Callable[[int, int, int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        plan = build_walk_forward_plan(
            dataset,
            from_date=from_date,
            to_date=to_date,
            folds=folds,
            train_ratio=train_ratio,
            rolling=rolling,
        )
        combo_total = combination_count(parameter_ranges)
        total_work = len(plan) * (combo_total + 1)
        completed_work = 0
        fold_results: list[dict[str, Any]] = []

        for fold in plan:
            if cancel_event is not None and cancel_event.is_set():
                raise OptimizationCancelled("walk-forward cancelled")

            fold_number = int(fold["fold"])

            def fold_progress(done: int, total: int, inflight: int) -> None:
                if progress is not None:
                    progress(
                        completed_work + done,
                        total_work,
                        fold_number,
                        inflight,
                        "TRAIN_OPTIMIZATION",
                    )

            sweep = self.run_sweep(
                dataset,
                from_date=fold["train_from"],
                to_date=fold["train_to"],
                parameter_ranges=parameter_ranges,
                cancel_event=cancel_event,
                progress=fold_progress,
            )
            completed_work += combo_total

            best = next(
                (
                    item
                    for item in sweep["candidates"]
                    if item["eligible"]
                ),
                None,
            )
            if best is None:
                raise OptimizerError(
                    f"fold {fold_number}: no eligible training candidate "
                    f"meeting min_trades={self.min_trades}"
                )

            test_profile = apply_parameters(
                self.base_profile,
                best["parameters"],
            )
            test_result = BacktestEngine(
                test_profile,
                initial_balance=self.initial_balance,
                spread_pips=self.spread_pips,
                commission_per_lot=self.commission_per_lot,
            ).run(
                dataset,
                from_date=fold["test_from"],
                to_date=fold["test_to"],
            )
            test_sharpe = trade_sample_sharpe(test_result)
            completed_work += 1

            if progress is not None:
                progress(
                    completed_work,
                    total_work,
                    fold_number,
                    0,
                    "TEST_EVALUATION",
                )

            fold_results.append(
                {
                    **fold,
                    "selection_source": "TRAIN_ONLY",
                    "leakage_guard_passed": True,
                    "best_parameters": deepcopy(best["parameters"]),
                    "train_score": best["score"],
                    "train_trade_sharpe": best["trade_sharpe"],
                    "train_result_hash": best["result_hash"],
                    "train_metrics": deepcopy(best["metrics"]),
                    "test_result_hash": test_result["result_hash"],
                    "test_trade_sharpe": test_sharpe,
                    "test_metrics": deepcopy(test_result["metrics"]),
                }
            )

        aggregate = walk_forward_aggregate(fold_results)
        deterministic = {
            "schema_version": OPTIMIZER_SCHEMA_VERSION,
            "mode": "WALK_FORWARD",
            "model": WALK_FORWARD_MODEL,
            "objective": OBJECTIVE_ID,
            "backtest_model": BACKTEST_MODEL,
            "base_profile_hash": self.base_profile_hash,
            "base_profile": deepcopy(self.base_profile),
            "dataset_file_name": dataset.path.name,
            "dataset_fingerprint": dataset.fingerprint,
            "dataset_metadata": dataset.metadata.public(),
            "from_date": str(from_date),
            "to_date": str(to_date),
            "initial_balance": self.initial_balance,
            "spread_pips": self.spread_pips,
            "commission_per_lot": self.commission_per_lot,
            "min_trades": self.min_trades,
            "parameter_ranges": [
                item.public()
                for item in parameter_ranges
            ],
            "combination_count_per_fold": combo_total,
            "folds": fold_results,
            "fold_count": len(fold_results),
            "train_ratio": float(train_ratio),
            "rolling": bool(rolling),
            "leakage_guard_passed": all(
                bool(item["leakage_guard_passed"])
                for item in fold_results
            ),
            "aggregate": aggregate,
        }
        deterministic["optimizer_hash"] = _optimizer_hash(
            deepcopy(deterministic)
        )
        deterministic["workers_used"] = self.max_workers
        return deterministic


def build_walk_forward_plan(
    dataset: HistoricalDataset,
    *,
    from_date: str,
    to_date: str,
    folds: int,
    train_ratio: float,
    rolling: bool,
) -> list[dict[str, Any]]:
    try:
        start = date.fromisoformat(str(from_date))
        end = date.fromisoformat(str(to_date))
    except ValueError as exc:
        raise OptimizerError("walk-forward dates must be YYYY-MM-DD") from exc
    if end < start:
        raise OptimizerError("to_date must be >= from_date")
    if not 2 <= int(folds) <= 20:
        raise OptimizerError("folds must be 2..20")
    if not 0.50 <= float(train_ratio) <= 0.90:
        raise OptimizerError("train_ratio must be 0.50..0.90")

    dates = sorted(
        {
            dataset.local_date(bar.time)
            for bar in dataset.bars
            if start <= dataset.local_date(bar.time) <= end
        }
    )
    if len(dates) < 4:
        raise OptimizerError("walk-forward requires at least four trading dates")

    train_count = int(math.floor(len(dates) * float(train_ratio)))
    train_count = max(1, min(train_count, len(dates) - 1))
    remaining = len(dates) - train_count
    if remaining < int(folds):
        raise OptimizerError(
            f"walk-forward has {remaining} out-of-sample dates, "
            f"fewer than requested folds={folds}"
        )

    base = remaining // int(folds)
    remainder = remaining % int(folds)
    test_sizes = [
        base + (1 if index < remainder else 0)
        for index in range(int(folds))
    ]

    cursor = train_count
    plan: list[dict[str, Any]] = []
    for index, test_size in enumerate(test_sizes, start=1):
        test_start_index = cursor
        test_end_index = cursor + test_size - 1
        train_end_index = test_start_index - 1
        train_start_index = (
            max(0, test_start_index - train_count)
            if rolling
            else 0
        )

        train_from = dates[train_start_index]
        train_to = dates[train_end_index]
        test_from = dates[test_start_index]
        test_to = dates[test_end_index]
        if train_to >= test_from:
            raise OptimizerError(
                f"walk-forward leakage guard failed at fold {index}"
            )

        plan.append(
            {
                "fold": index,
                "train_from": train_from.isoformat(),
                "train_to": train_to.isoformat(),
                "test_from": test_from.isoformat(),
                "test_to": test_to.isoformat(),
                "train_date_count": train_end_index - train_start_index + 1,
                "test_date_count": test_size,
                "rolling": bool(rolling),
            }
        )
        cursor = test_end_index + 1

    return plan


def walk_forward_aggregate(
    folds: list[dict[str, Any]],
) -> dict[str, Any]:
    if not folds:
        raise OptimizerError("walk-forward has no fold results")

    net = [
        float(item["test_metrics"]["net_profit"])
        for item in folds
    ]
    net_pct = [
        float(item["test_metrics"]["net_profit_pct"])
        for item in folds
    ]
    sharpes = [
        float(item["test_trade_sharpe"])
        for item in folds
    ]
    win_rates = [
        float(item["test_metrics"]["win_rate"])
        for item in folds
    ]
    drawdowns = [
        float(item["test_metrics"]["max_drawdown_pct"])
        for item in folds
    ]
    pfs = [
        float(item["test_metrics"]["profit_factor"])
        for item in folds
        if item["test_metrics"].get("profit_factor") is not None
    ]

    positive_ratio = sum(1 for value in net if value > 0) / len(net)
    mean_return = statistics.fmean(net_pct)
    dispersion = statistics.pstdev(net_pct) if len(net_pct) > 1 else 0.0
    denominator = abs(mean_return) + dispersion
    consistency = (
        1.0
        if denominator <= 1e-12
        else max(0.0, min(1.0, 1.0 - dispersion / denominator))
    )
    stability = 0.5 * positive_ratio + 0.5 * consistency

    return {
        "average_net_profit": round(statistics.fmean(net), 8),
        "average_net_profit_pct": round(mean_return, 8),
        "average_trade_sharpe": round(statistics.fmean(sharpes), 8),
        "average_win_rate": round(statistics.fmean(win_rates), 8),
        "average_max_drawdown_pct": round(statistics.fmean(drawdowns), 8),
        "average_profit_factor": (
            round(statistics.fmean(pfs), 8)
            if pfs
            else None
        ),
        "positive_fold_ratio": round(positive_ratio, 8),
        "stability": round(stability, 8),
    }


class OptimizerRepository:
    def __init__(
        self,
        root_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        self.root_dir = (
            Path(root_dir).expanduser()
            if root_dir is not None
            else default_optimizer_directory()
        )
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save(self, result: dict[str, Any]) -> dict[str, Any]:
        run_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        stored = {
            **deepcopy(result),
            "run_id": run_id,
            "created_at_utc": created_at,
        }
        path = self.root_dir / f"{run_id}.json"
        temp = path.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(
                stored,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        temp.replace(path)
        return stored

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise OptimizerError("history limit must be 1..500")

        items: list[dict[str, Any]] = []
        for path in self.root_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            mode = payload.get("mode")
            if mode not in {"SWEEP", "WALK_FORWARD"}:
                continue

            summary: dict[str, Any]
            if mode == "SWEEP":
                candidates = payload.get("candidates")
                top = (
                    next(
                        (
                            item
                            for item in candidates
                            if isinstance(item, dict)
                            and item.get("eligible")
                        ),
                        None,
                    )
                    if isinstance(candidates, list)
                    else None
                )
                summary = {
                    "combination_count": payload.get("combination_count"),
                    "eligible_count": payload.get("eligible_count"),
                    "top_candidate": deepcopy(top),
                }
            else:
                summary = {
                    "fold_count": payload.get("fold_count"),
                    "aggregate": deepcopy(payload.get("aggregate")),
                    "leakage_guard_passed": payload.get(
                        "leakage_guard_passed"
                    ),
                }

            items.append(
                {
                    "run_id": payload.get("run_id"),
                    "created_at_utc": payload.get("created_at_utc"),
                    "mode": mode,
                    "model": payload.get("model"),
                    "objective": payload.get("objective"),
                    "optimizer_hash": payload.get("optimizer_hash"),
                    "base_profile_hash": payload.get("base_profile_hash"),
                    "dataset_file_name": payload.get("dataset_file_name"),
                    "dataset_fingerprint": payload.get("dataset_fingerprint"),
                    "from_date": payload.get("from_date"),
                    "to_date": payload.get("to_date"),
                    "summary": summary,
                }
            )

        items.sort(
            key=lambda item: str(item.get("created_at_utc") or ""),
            reverse=True,
        )
        return items[:limit]

    def get(self, run_id: str) -> dict[str, Any]:
        path = self._run_path(run_id)
        if not path.is_file():
            raise OptimizerError("optimizer result does not exist")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OptimizerError("stored optimizer result is corrupt") from exc
        if not isinstance(payload, dict):
            raise OptimizerError("stored optimizer result root is invalid")
        return payload

    def delete(self, run_id: str) -> bool:
        path = self._run_path(run_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _run_path(self, run_id: str) -> Path:
        try:
            parsed = UUID(str(run_id).strip())
        except ValueError as exc:
            raise OptimizerError("run_id must be UUID") from exc
        return self.root_dir / f"{parsed}.json"


def heatmap_from_result(
    result: dict[str, Any],
    *,
    x_path: str,
    y_path: str,
    metric: str,
) -> dict[str, Any]:
    if result.get("mode") != "SWEEP":
        raise OptimizerError("heatmap is available for SWEEP results only")
    if metric not in HEATMAP_METRICS:
        raise OptimizerError(f"unsupported heatmap metric: {metric}")
    if x_path == y_path:
        raise OptimizerError("heatmap X and Y parameters must differ")

    ranges = {
        str(item.get("path")): item
        for item in result.get("parameter_ranges", [])
        if isinstance(item, dict)
    }
    if x_path not in ranges or y_path not in ranges:
        raise OptimizerError("heatmap axes must be optimized parameters")

    x_values = list(ranges[x_path].get("values", []))
    y_values = list(ranges[y_path].get("values", []))
    buckets: dict[tuple[str, str], list[float]] = {}

    for candidate in result.get("candidates", []):
        if not isinstance(candidate, dict) or not candidate.get("eligible"):
            continue
        parameters = candidate.get("parameters")
        if not isinstance(parameters, dict):
            continue
        if x_path not in parameters or y_path not in parameters:
            continue
        value = _candidate_metric(candidate, metric)
        if value is None:
            continue
        key = (
            json.dumps(parameters[x_path], sort_keys=True),
            json.dumps(parameters[y_path], sort_keys=True),
        )
        buckets.setdefault(key, []).append(value)

    cells: list[dict[str, Any]] = []
    for x in x_values:
        for y in y_values:
            key = (
                json.dumps(x, sort_keys=True),
                json.dumps(y, sort_keys=True),
            )
            values = buckets.get(key, [])
            cells.append(
                {
                    "x": x,
                    "y": y,
                    "value": (
                        round(statistics.fmean(values), 8)
                        if values
                        else None
                    ),
                    "samples": len(values),
                }
            )

    present = [
        float(item["value"])
        for item in cells
        if item["value"] is not None
    ]
    return {
        "x_path": x_path,
        "y_path": y_path,
        "metric": metric,
        "higher_is_better": metric != "max_drawdown_pct",
        "x_values": x_values,
        "y_values": y_values,
        "cells": cells,
        "min_value": min(present) if present else None,
        "max_value": max(present) if present else None,
    }


def _candidate_metric(
    candidate: dict[str, Any],
    metric: str,
) -> float | None:
    if metric == "score":
        value = candidate.get("score")
    elif metric == "trade_sharpe":
        value = candidate.get("trade_sharpe")
    else:
        metrics = candidate.get("metrics")
        value = metrics.get(metric) if isinstance(metrics, dict) else None
    if value is None:
        return None
    return float(value)


class OptimizerJobManager:
    def __init__(
        self,
        repository: OptimizerRepository,
        *,
        journal_callback: Callable[..., None] | None = None,
    ) -> None:
        self.repository = repository
        self.journal_callback = journal_callback
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._active_job_id: str | None = None
        self._cancel_events: dict[str, threading.Event] = {}

    def start_sweep(
        self,
        request: dict[str, Any],
        base_profile: dict[str, Any],
    ) -> dict[str, Any]:
        return self._start(
            mode="SWEEP",
            request=request,
            base_profile=base_profile,
        )

    def start_walk_forward(
        self,
        request: dict[str, Any],
        base_profile: dict[str, Any],
    ) -> dict[str, Any]:
        return self._start(
            mode="WALK_FORWARD",
            request=request,
            base_profile=base_profile,
        )

    def _start(
        self,
        *,
        mode: str,
        request: dict[str, Any],
        base_profile: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            if self._active_job_id is not None:
                active = self._jobs.get(self._active_job_id)
                if active and active["status"] in {"QUEUED", "RUNNING", "STOPPING"}:
                    raise OptimizerError(
                        f"optimizer job already active: {self._active_job_id}"
                    )

        path = request.get("path")
        if not isinstance(path, str) or not path.strip():
            raise OptimizerError("path is required")
        dataset = load_historical_dataset(path)
        ranges = parse_parameter_ranges(
            request.get("parameter_ranges"),
            base_profile,
        )
        combos = combination_count(ranges)

        initial_balance = float(request.get("initial_balance", 10_000.0))
        spread_pips = float(request.get("spread_pips", 20.0))
        commission_per_lot = float(
            request.get("commission_per_lot", 7.0)
        )
        min_trades = int(request.get("min_trades", 20))
        workers = int(request.get("max_workers", 1))
        from_date = str(request.get("from_date", "")).strip()
        to_date = str(request.get("to_date", "")).strip()

        engine = OptimizerEngine(
            base_profile,
            initial_balance=initial_balance,
            spread_pips=spread_pips,
            commission_per_lot=commission_per_lot,
            min_trades=min_trades,
            max_workers=workers,
        )

        plan: list[dict[str, Any]] | None = None
        total_work = combos
        folds = None
        train_ratio = None
        rolling = None
        if mode == "WALK_FORWARD":
            folds = int(request.get("folds", 5))
            train_ratio = float(request.get("train_ratio", 0.70))
            rolling = bool(request.get("rolling", True))
            plan = build_walk_forward_plan(
                dataset,
                from_date=from_date,
                to_date=to_date,
                folds=folds,
                train_ratio=train_ratio,
                rolling=rolling,
            )
            total_work = len(plan) * (combos + 1)

        job_id = str(uuid4())
        cancel_event = threading.Event()
        now = datetime.now(timezone.utc).isoformat()
        state = {
            "job_id": job_id,
            "mode": mode,
            "status": "QUEUED",
            "created_at_utc": now,
            "started_at_utc": None,
            "finished_at_utc": None,
            "dataset_file_name": dataset.path.name,
            "dataset_fingerprint": dataset.fingerprint,
            "base_profile_hash": engine.base_profile_hash,
            "objective": OBJECTIVE_ID,
            "combination_count": combos,
            "total_work": total_work,
            "completed_work": 0,
            "in_flight": 0,
            "workers": engine.max_workers,
            "current_fold": 0,
            "fold_count": len(plan) if plan is not None else 0,
            "phase": "QUEUED",
            "elapsed_seconds": 0.0,
            "speed_per_minute": 0.0,
            "eta_seconds": None,
            "result_run_id": None,
            "optimizer_hash": None,
            "error": None,
            "parameter_ranges": [
                item.public()
                for item in ranges
            ],
        }

        with self._lock:
            self._jobs[job_id] = state
            self._cancel_events[job_id] = cancel_event
            self._active_job_id = job_id

        thread = threading.Thread(
            target=self._run_job,
            args=(
                job_id,
                mode,
                engine,
                dataset,
                ranges,
                from_date,
                to_date,
                folds,
                train_ratio,
                rolling,
                cancel_event,
            ),
            name=f"xaupy-optimizer-{job_id[:8]}",
            daemon=True,
        )
        thread.start()
        return self.status(job_id)

    def _run_job(
        self,
        job_id: str,
        mode: str,
        engine: OptimizerEngine,
        dataset: HistoricalDataset,
        ranges: tuple[ParameterRange, ...],
        from_date: str,
        to_date: str,
        folds: int | None,
        train_ratio: float | None,
        rolling: bool | None,
        cancel_event: threading.Event,
    ) -> None:
        started = time.monotonic()
        with self._lock:
            state = self._jobs[job_id]
            state["status"] = "RUNNING"
            state["phase"] = (
                "PARAMETER_SWEEP"
                if mode == "SWEEP"
                else "WALK_FORWARD"
            )
            state["started_at_utc"] = datetime.now(timezone.utc).isoformat()

        self._journal(
            "OPTIMIZER_START" if mode == "SWEEP" else "WALK_FORWARD_START",
            f"{mode} optimization started",
            {
                "job_id": job_id,
                "dataset_fingerprint": dataset.fingerprint,
                "base_profile_hash": engine.base_profile_hash,
                "combination_count": combination_count(ranges),
                "parameter_ranges": [item.public() for item in ranges],
                "from_date": from_date,
                "to_date": to_date,
                "folds": folds,
                "train_ratio": train_ratio,
                "rolling": rolling,
            },
        )

        def sweep_progress(done: int, total: int, inflight: int) -> None:
            self._update_progress(
                job_id,
                done,
                total,
                inflight,
                0,
                "PARAMETER_SWEEP",
                started,
            )

        def wf_progress(
            done: int,
            total: int,
            fold: int,
            inflight: int,
            phase: str,
        ) -> None:
            self._update_progress(
                job_id,
                done,
                total,
                inflight,
                fold,
                phase,
                started,
            )

        try:
            if mode == "SWEEP":
                result = engine.run_sweep(
                    dataset,
                    from_date=from_date,
                    to_date=to_date,
                    parameter_ranges=ranges,
                    cancel_event=cancel_event,
                    progress=sweep_progress,
                )
            else:
                assert folds is not None
                assert train_ratio is not None
                assert rolling is not None
                result = engine.walk_forward(
                    dataset,
                    from_date=from_date,
                    to_date=to_date,
                    parameter_ranges=ranges,
                    folds=folds,
                    train_ratio=train_ratio,
                    rolling=rolling,
                    cancel_event=cancel_event,
                    progress=wf_progress,
                )

            stored = self.repository.save(result)
            with self._lock:
                state = self._jobs[job_id]
                state["status"] = "COMPLETED"
                state["phase"] = "COMPLETED"
                state["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
                state["completed_work"] = state["total_work"]
                state["in_flight"] = 0
                state["result_run_id"] = stored["run_id"]
                state["optimizer_hash"] = stored["optimizer_hash"]
                state["elapsed_seconds"] = round(time.monotonic() - started, 3)
                state["eta_seconds"] = 0.0

            self._journal(
                "OPTIMIZER_COMPLETE" if mode == "SWEEP" else "WALK_FORWARD_COMPLETE",
                f"{mode} optimization completed",
                {
                    "job_id": job_id,
                    "run_id": stored["run_id"],
                    "optimizer_hash": stored["optimizer_hash"],
                    "mode": mode,
                    "summary": (
                        {
                            "combination_count": stored.get("combination_count"),
                            "eligible_count": stored.get("eligible_count"),
                        }
                        if mode == "SWEEP"
                        else stored.get("aggregate")
                    ),
                    "leakage_guard_passed": stored.get(
                        "leakage_guard_passed"
                    ),
                },
            )
        except OptimizationCancelled:
            with self._lock:
                state = self._jobs[job_id]
                state["status"] = "CANCELLED"
                state["phase"] = "CANCELLED"
                state["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
                state["in_flight"] = 0
                state["elapsed_seconds"] = round(time.monotonic() - started, 3)
                state["eta_seconds"] = None
            self._journal(
                "OPTIMIZER_CANCELLED",
                f"{mode} optimization cancelled",
                {"job_id": job_id},
            )
        except Exception as exc:  # job boundary must surface deterministic error
            with self._lock:
                state = self._jobs[job_id]
                state["status"] = "FAILED"
                state["phase"] = "FAILED"
                state["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
                state["in_flight"] = 0
                state["elapsed_seconds"] = round(time.monotonic() - started, 3)
                state["eta_seconds"] = None
                state["error"] = str(exc)
            self._journal(
                "OPTIMIZER_FAILED" if mode == "SWEEP" else "WALK_FORWARD_FAILED",
                f"{mode} optimization failed",
                {"job_id": job_id, "error": str(exc)},
            )
        finally:
            with self._lock:
                if self._active_job_id == job_id:
                    self._active_job_id = None

    def _update_progress(
        self,
        job_id: str,
        completed: int,
        total: int,
        inflight: int,
        fold: int,
        phase: str,
        started: float,
    ) -> None:
        elapsed = max(0.001, time.monotonic() - started)
        speed_per_second = completed / elapsed
        eta = (
            (total - completed) / speed_per_second
            if speed_per_second > 1e-12
            else None
        )
        with self._lock:
            state = self._jobs[job_id]
            state["completed_work"] = completed
            state["total_work"] = total
            state["in_flight"] = inflight
            state["current_fold"] = fold
            state["phase"] = phase
            state["elapsed_seconds"] = round(elapsed, 3)
            state["speed_per_minute"] = round(speed_per_second * 60.0, 3)
            state["eta_seconds"] = (
                round(eta, 3)
                if eta is not None
                else None
            )
            if state["status"] == "STOPPING":
                state["phase"] = "STOPPING"

    def status(self, job_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            target = job_id or self._active_job_id
            if target is None:
                return {
                    "job_id": None,
                    "mode": None,
                    "status": "IDLE",
                    "phase": "IDLE",
                    "completed_work": 0,
                    "total_work": 0,
                    "in_flight": 0,
                    "workers": 0,
                    "progress_pct": 0.0,
                    "speed_per_minute": 0.0,
                    "eta_seconds": None,
                    "elapsed_seconds": 0.0,
                    "result_run_id": None,
                    "optimizer_hash": None,
                    "error": None,
                }
            if target not in self._jobs:
                raise OptimizerError("optimizer job does not exist")
            state = deepcopy(self._jobs[target])

        total = int(state.get("total_work", 0))
        completed = int(state.get("completed_work", 0))
        state["progress_pct"] = (
            round(completed / total * 100.0, 3)
            if total > 0
            else 0.0
        )
        return state

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                raise OptimizerError("optimizer job does not exist")
            if state["status"] not in {"QUEUED", "RUNNING", "STOPPING"}:
                return deepcopy(state)
            state["status"] = "STOPPING"
            state["phase"] = "STOPPING"
            cancel_event = self._cancel_events[job_id]
            cancel_event.set()
        return self.status(job_id)

    def _journal(
        self,
        tag: str,
        message: str,
        details: dict[str, Any],
    ) -> None:
        if self.journal_callback is None:
            return
        try:
            self.journal_callback(tag, message, details)
        except Exception:
            pass
