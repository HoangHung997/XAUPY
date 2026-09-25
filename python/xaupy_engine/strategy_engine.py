from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

from .config_schema import TIMEFRAME_OPTIONS, default_profile, normalized_profile


class StrategyDataError(ValueError):
    """Raised when strategy market data is structurally invalid."""


@dataclass(frozen=True)
class Bar:
    time: int
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Bar":
        try:
            timestamp = int(payload["time"])
            open_price = float(payload["open"])
            high = float(payload["high"])
            low = float(payload["low"])
            close = float(payload["close"])
            tick_volume = int(payload.get("tick_volume", 0))
        except (KeyError, TypeError, ValueError) as exc:
            raise StrategyDataError(f"invalid bar payload: {exc}") from exc

        values = (open_price, high, low, close)
        if timestamp <= 0:
            raise StrategyDataError("bar time must be positive")
        if not all(math.isfinite(value) for value in values):
            raise StrategyDataError("bar OHLC values must be finite")
        if high < low:
            raise StrategyDataError("bar high must be >= low")
        if high < max(open_price, close) or low > min(open_price, close):
            raise StrategyDataError("bar OHLC range is inconsistent")
        if tick_volume < 0:
            raise StrategyDataError("bar tick_volume must be >= 0")

        return cls(timestamp, open_price, high, low, close, tick_volume)


def _price(bar: Bar, source: str) -> float:
    source = source.upper()
    if source == "CLOSE":
        return bar.close
    if source == "OPEN":
        return bar.open
    if source == "HIGH":
        return bar.high
    if source == "LOW":
        return bar.low
    if source == "MEDIAN":
        return (bar.high + bar.low) / 2.0
    if source == "TYPICAL":
        return (bar.high + bar.low + bar.close) / 3.0
    if source == "WEIGHTED":
        return (bar.high + bar.low + (2.0 * bar.close)) / 4.0
    raise ValueError(f"unsupported price source: {source}")


def _moving_average(values: list[float], period: int, ma_type: str) -> float | None:
    if period <= 0 or len(values) < period:
        return None

    ma_type = ma_type.upper()
    if ma_type == "SMA":
        return sum(values[-period:]) / period

    if ma_type == "LWMA":
        window = values[-period:]
        denominator = period * (period + 1) / 2.0
        return sum(value * weight for weight, value in enumerate(window, start=1)) / denominator

    seed = sum(values[:period]) / period
    if ma_type == "EMA":
        alpha = 2.0 / (period + 1.0)
        result = seed
        for value in values[period:]:
            result = (value * alpha) + (result * (1.0 - alpha))
        return result

    if ma_type == "SMMA":
        result = seed
        for value in values[period:]:
            result = ((result * (period - 1)) + value) / period
        return result

    raise ValueError(f"unsupported MA type: {ma_type}")


def _rsi(values: list[float], period: int) -> float | None:
    if period <= 0 or len(values) < period + 1:
        return None

    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]

    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    for index in range(period, len(changes)):
        average_gain = ((average_gain * (period - 1)) + gains[index]) / period
        average_loss = ((average_loss * (period - 1)) + losses[index]) / period

    if average_loss == 0.0:
        if average_gain == 0.0:
            return 50.0
        return 100.0

    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _zscore(values: list[float], period: int) -> float | None:
    if period <= 1 or len(values) < period:
        return None

    window = values[-period:]
    mean = sum(window) / period
    variance = sum((value - mean) ** 2 for value in window) / period
    deviation = math.sqrt(variance)
    if deviation == 0.0:
        return 0.0
    return (window[-1] - mean) / deviation


def _true_ranges(bars: list[Bar]) -> list[float]:
    result: list[float] = []
    for index in range(1, len(bars)):
        current = bars[index]
        previous = bars[index - 1]
        result.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return result


def _atr(bars: list[Bar], period: int) -> float | None:
    ranges = _true_ranges(bars)
    if period <= 0 or len(ranges) < period:
        return None

    result = sum(ranges[:period]) / period
    for value in ranges[period:]:
        result = ((result * (period - 1)) + value) / period
    return result


def _adx(bars: list[Bar], period: int) -> float | None:
    if period <= 1 or len(bars) < (period * 2):
        return None

    true_ranges: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []

    for index in range(1, len(bars)):
        current = bars[index]
        previous = bars[index - 1]
        up_move = current.high - previous.high
        down_move = previous.low - current.low

        plus_dm.append(up_move if up_move > down_move and up_move > 0.0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0.0 else 0.0)
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )

    if len(true_ranges) < period:
        return None

    smoothed_tr = sum(true_ranges[:period])
    smoothed_plus = sum(plus_dm[:period])
    smoothed_minus = sum(minus_dm[:period])
    dx_values: list[float] = []

    def append_dx() -> None:
        if smoothed_tr <= 0.0:
            dx_values.append(0.0)
            return
        plus_di = 100.0 * smoothed_plus / smoothed_tr
        minus_di = 100.0 * smoothed_minus / smoothed_tr
        denominator = plus_di + minus_di
        dx_values.append(0.0 if denominator == 0.0 else 100.0 * abs(plus_di - minus_di) / denominator)

    append_dx()
    for index in range(period, len(true_ranges)):
        smoothed_tr = smoothed_tr - (smoothed_tr / period) + true_ranges[index]
        smoothed_plus = smoothed_plus - (smoothed_plus / period) + plus_dm[index]
        smoothed_minus = smoothed_minus - (smoothed_minus / period) + minus_dm[index]
        append_dx()

    if len(dx_values) < period:
        return None

    result = sum(dx_values[:period]) / period
    for value in dx_values[period:]:
        result = ((result * (period - 1)) + value) / period
    return result


def _logic(values: list[bool], mode: str) -> bool:
    if not values:
        return True
    if mode == "OR":
        return any(values)
    return all(values)


class StrategyEngine:
    """Deterministic Direction -> Pullback -> Trigger research state machine.

    The engine only produces strategy state and signal intents. It never sends orders.
    """

    def __init__(
        self,
        profile: dict[str, Any] | None = None,
        *,
        max_history: int = 4096,
    ) -> None:
        if max_history < 256:
            raise ValueError("max_history must be >= 256")

        self.max_history = max_history
        self.history: dict[str, list[Bar]] = {timeframe: [] for timeframe in TIMEFRAME_OPTIONS}
        self.profile: dict[str, Any] = {}
        self.profile_hash = ""
        self.state = "WARMUP"
        self.direction = "NEUTRAL"
        self.armed_side: str | None = None
        self._armed_trigger_time: int | None = None
        self._trigger_rsi_extreme: float | None = None
        self._trigger_z_extreme: float | None = None
        self.signal_sequence = 0
        self.last_signal: dict[str, Any] | None = None
        self.last_metrics: dict[str, Any] = {}
        self.last_conditions: dict[str, Any] = {}
        self.warmup_reasons: list[str] = []
        self.blocked_reason: str | None = "NO_MARKET_DATA"
        self.last_data_error: str | None = None
        self.last_reset_reason: str | None = None
        self._last_evaluated_trigger_time: int | None = None

        self.set_profile(profile or default_profile(), retain_history=False)

    def set_profile(self, profile: dict[str, Any], *, retain_history: bool = True) -> None:
        normalized = normalized_profile(profile)
        encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        profile_hash = hashlib.sha256(encoded).hexdigest()

        changed = profile_hash != self.profile_hash
        self.profile = normalized
        self.profile_hash = profile_hash

        if not retain_history:
            self.history = {timeframe: [] for timeframe in TIMEFRAME_OPTIONS}

        if changed:
            self.reset_setup("PROFILE_CHANGED")

    def reset_setup(self, reason: str) -> None:
        self.state = "WARMUP"
        self.direction = "NEUTRAL"
        self.armed_side = None
        self._armed_trigger_time = None
        self._trigger_rsi_extreme = None
        self._trigger_z_extreme = None
        self.last_signal = None
        self.last_conditions = {}
        self.warmup_reasons = []
        self.blocked_reason = reason
        self.last_reset_reason = reason
        self._last_evaluated_trigger_time = None

    def ingest_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise StrategyDataError("strategy snapshot must be an object")

        symbol = payload.get("symbol")
        expected_symbol = self.profile["strategy"]["symbol"]
        if isinstance(symbol, str) and symbol and symbol != expected_symbol:
            self.blocked_reason = "SYMBOL_MISMATCH"
            self.last_data_error = f"expected symbol {expected_symbol}, got {symbol}"
            return self.status_payload(market_connected=True)

        bars_payload = payload.get("bars")
        if not isinstance(bars_payload, dict):
            raise StrategyDataError("strategy snapshot bars must be an object")

        new_timeframes: set[str] = set()
        errors: list[str] = []

        for timeframe in TIMEFRAME_OPTIONS:
            raw = bars_payload.get(timeframe)
            if raw is None:
                continue
            if not isinstance(raw, dict):
                errors.append(f"{timeframe}: bar must be object or null")
                continue

            try:
                bar = Bar.from_payload(raw)
            except StrategyDataError as exc:
                errors.append(f"{timeframe}: {exc}")
                continue

            history = self.history[timeframe]
            if not history or bar.time > history[-1].time:
                history.append(bar)
                if len(history) > self.max_history:
                    del history[: len(history) - self.max_history]
                new_timeframes.add(timeframe)
            elif bar.time == history[-1].time:
                history[-1] = bar
            # Older out-of-order bars are ignored. The Bridge repeatedly publishes
            # the latest closed bar, so back-filling an older bar here would make the
            # state machine non-deterministic.

        self.last_data_error = "; ".join(errors) if errors else None
        if new_timeframes:
            self._evaluate(new_timeframes)

        return self.status_payload(market_connected=True)

    def _evaluate(self, new_timeframes: set[str]) -> None:
        metrics, warmup = self._metrics()
        self.last_metrics = metrics
        self.warmup_reasons = warmup

        if warmup:
            self.state = "WARMUP"
            self.direction = "NEUTRAL"
            self.blocked_reason = "WARMUP"
            self.armed_side = None
            self._armed_trigger_time = None
            self._trigger_rsi_extreme = None
            self._trigger_z_extreme = None
            return

        direction_sides, direction_label, filter_reason = self._direction_sides(metrics)
        self.direction = direction_label

        if filter_reason is not None:
            self.state = "FILTER_BLOCKED"
            self.blocked_reason = filter_reason
            self.armed_side = None
            self._armed_trigger_time = None
            self._trigger_rsi_extreme = None
            self._trigger_z_extreme = None
            return

        if not direction_sides:
            self.state = "WAIT_DIRECTION"
            self.blocked_reason = "DIRECTION_NEUTRAL"
            self.armed_side = None
            self._armed_trigger_time = None
            self._trigger_rsi_extreme = None
            self._trigger_z_extreme = None
            return

        pullback = {
            side: self._pullback_pass(side, metrics)
            for side in sorted(direction_sides)
        }
        self.last_conditions["pullback"] = deepcopy(pullback)

        if self.armed_side is not None and self.armed_side not in direction_sides:
            self._clear_arm("DIRECTION_CHANGED")

        if self.armed_side is not None and not pullback.get(self.armed_side, False):
            self._clear_arm("PULLBACK_RESET")

        candidates = [side for side in sorted(direction_sides) if pullback.get(side, False)]

        if self.armed_side is None:
            if len(candidates) > 1:
                self.state = "AMBIGUOUS"
                self.blocked_reason = "BOTH_SIDES_VALID"
                return
            if len(candidates) == 1:
                self._arm(candidates[0], metrics)
            else:
                suffix = direction_label if direction_label in {"BUY", "SELL"} else "BOTH"
                self.state = f"WAIT_PULLBACK_{suffix}"
                self.blocked_reason = "WAIT_PULLBACK"
                return

        assert self.armed_side is not None

        trigger_tf = self.profile["timeframes"]["trigger"]
        trigger_bar = self.history[trigger_tf][-1]
        if trigger_tf not in new_timeframes:
            self.blocked_reason = "WAIT_TRIGGER_BAR"
            if not self.state.startswith("TRIGGERED_"):
                self.state = f"ARMED_{self.armed_side}"
            return

        if self._armed_trigger_time is not None and trigger_bar.time <= self._armed_trigger_time:
            self.state = f"ARMED_{self.armed_side}"
            self.blocked_reason = "WAIT_TRIGGER_BAR"
            return

        if self.state.startswith("TRIGGERED_"):
            self.blocked_reason = "WAIT_PULLBACK_RESET"
            return

        self._update_trigger_extremes(self.armed_side, metrics)
        trigger_pass, details = self._trigger_pass(self.armed_side, metrics)
        self.last_conditions["trigger"] = details

        if not trigger_pass:
            self.state = f"ARMED_{self.armed_side}"
            self.blocked_reason = "WAIT_TRIGGER_REVERSAL"
            self._last_evaluated_trigger_time = trigger_bar.time
            return

        self.signal_sequence += 1
        self.state = f"TRIGGERED_{self.armed_side}"
        self.blocked_reason = None
        self._last_evaluated_trigger_time = trigger_bar.time
        self.last_signal = {
            "sequence": self.signal_sequence,
            "side": self.armed_side,
            "bar_time": trigger_bar.time,
            "profile_hash": self.profile_hash,
            "direction": self.direction,
            "timeframes": deepcopy(self.profile["timeframes"]),
            "indicators": deepcopy(metrics),
        }

    def _clear_arm(self, reason: str) -> None:
        self.armed_side = None
        self._armed_trigger_time = None
        self._trigger_rsi_extreme = None
        self._trigger_z_extreme = None
        self.state = "WAIT_DIRECTION"
        self.blocked_reason = reason

    def _arm(self, side: str, metrics: dict[str, Any]) -> None:
        trigger_tf = self.profile["timeframes"]["trigger"]
        trigger_bar = self.history[trigger_tf][-1]
        self.armed_side = side
        self._armed_trigger_time = trigger_bar.time
        self._trigger_rsi_extreme = metrics["trigger"].get("rsi")
        self._trigger_z_extreme = metrics["trigger"].get("z")
        self.state = f"ARMED_{side}"
        self.blocked_reason = "WAIT_TRIGGER_REVERSAL"

    def _update_trigger_extremes(self, side: str, metrics: dict[str, Any]) -> None:
        current_rsi = metrics["trigger"].get("rsi")
        current_z = metrics["trigger"].get("z")

        if current_rsi is not None:
            if self._trigger_rsi_extreme is None:
                self._trigger_rsi_extreme = current_rsi
            elif side == "BUY":
                self._trigger_rsi_extreme = min(self._trigger_rsi_extreme, current_rsi)
            else:
                self._trigger_rsi_extreme = max(self._trigger_rsi_extreme, current_rsi)

        if current_z is not None:
            if self._trigger_z_extreme is None:
                self._trigger_z_extreme = current_z
            elif side == "BUY":
                self._trigger_z_extreme = min(self._trigger_z_extreme, current_z)
            else:
                self._trigger_z_extreme = max(self._trigger_z_extreme, current_z)

    def _trigger_pass(self, side: str, metrics: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        cfg = self.profile["trigger"]
        conditions: list[bool] = []
        detail: dict[str, Any] = {"side": side, "logic": cfg["logic"]}

        if cfg["rsi_enabled"]:
            current = metrics["trigger"]["rsi"]
            extreme = self._trigger_rsi_extreme
            assert current is not None and extreme is not None
            move = current - extreme if side == "BUY" else extreme - current
            passed = move >= cfg["rsi_reversal_delta"]
            detail["rsi"] = {
                "current": current,
                "extreme": extreme,
                "reversal": move,
                "required": cfg["rsi_reversal_delta"],
                "passed": passed,
            }
            conditions.append(passed)

        if cfg["z_enabled"]:
            current = metrics["trigger"]["z"]
            extreme = self._trigger_z_extreme
            assert current is not None and extreme is not None
            move = current - extreme if side == "BUY" else extreme - current
            passed = move >= cfg["z_reversal_delta"]
            detail["z"] = {
                "current": current,
                "extreme": extreme,
                "reversal": move,
                "required": cfg["z_reversal_delta"],
                "passed": passed,
            }
            conditions.append(passed)

        passed = _logic(conditions, cfg["logic"])
        detail["passed"] = passed
        return passed, detail

    def _pullback_pass(self, side: str, metrics: dict[str, Any]) -> bool:
        cfg = self.profile["pullback"]
        conditions: list[bool] = []

        if cfg["rsi_enabled"]:
            rsi_value = metrics["pullback"]["rsi"]
            assert rsi_value is not None
            conditions.append(
                rsi_value <= cfg["rsi_buy_level"]
                if side == "BUY"
                else rsi_value >= cfg["rsi_sell_level"]
            )

        if cfg["z_enabled"]:
            z_value = metrics["pullback"]["z"]
            assert z_value is not None
            conditions.append(
                z_value <= cfg["z_buy_level"]
                if side == "BUY"
                else z_value >= cfg["z_sell_level"]
            )

        return _logic(conditions, cfg["logic"])

    def _direction_sides(
        self,
        metrics: dict[str, Any],
    ) -> tuple[set[str], str, str | None]:
        cfg = self.profile
        direction_cfg = cfg["direction"]
        direction_bar = self.history[cfg["timeframes"]["direction"]][-1]

        if direction_cfg["ma_enabled"]:
            current_ma = metrics["direction"]["ma"]
            assert current_ma is not None
            if direction_cfg["require_close_side"]:
                if direction_bar.close > current_ma:
                    sides = {"BUY"}
                elif direction_bar.close < current_ma:
                    sides = {"SELL"}
                else:
                    sides = set()
            else:
                previous_ma = metrics["direction"]["ma_previous"]
                assert previous_ma is not None
                if current_ma > previous_ma:
                    sides = {"BUY"}
                elif current_ma < previous_ma:
                    sides = {"SELL"}
                else:
                    sides = set()
        else:
            sides = {"BUY", "SELL"}

        if direction_cfg["open_filter_enabled"] and direction_cfg["open_reference_mode"] != "NONE":
            reference = metrics["direction"]["open_reference"]
            assert reference is not None
            sides = {
                side
                for side in sides
                if (
                    direction_bar.close >= reference
                    if side == "BUY"
                    else direction_bar.close <= reference
                )
            }

        adx_cfg = cfg["filters"]["adx"]
        if adx_cfg["enabled"]:
            value = metrics["filters"]["adx"]
            assert value is not None
            if not (adx_cfg["min"] <= value <= adx_cfg["max"]):
                return set(), self._label_sides(sides), "ADX_FILTER"

        atr_cfg = cfg["filters"]["atr"]
        if atr_cfg["enabled"]:
            value = metrics["filters"]["atr"]
            assert value is not None
            if not (atr_cfg["min_price_units"] <= value <= atr_cfg["max_price_units"]):
                return set(), self._label_sides(sides), "ATR_FILTER"

        open_cfg = cfg["filters"]["open"]
        if open_cfg["enabled"] and open_cfg["reference_mode"] != "NONE":
            reference = metrics["filters"]["open_reference"]
            assert reference is not None
            buffer_value = open_cfg["buffer_price_units"]
            sides = {
                side
                for side in sides
                if (
                    direction_bar.close >= reference + buffer_value
                    if side == "BUY"
                    else direction_bar.close <= reference - buffer_value
                )
            }

        if not cfg["strategy"]["allow_buy"]:
            sides.discard("BUY")
        if not cfg["strategy"]["allow_sell"]:
            sides.discard("SELL")

        return sides, self._label_sides(sides), None

    @staticmethod
    def _label_sides(sides: set[str]) -> str:
        if sides == {"BUY"}:
            return "BUY"
        if sides == {"SELL"}:
            return "SELL"
        if sides == {"BUY", "SELL"}:
            return "BOTH"
        return "NEUTRAL"

    def _metrics(self) -> tuple[dict[str, Any], list[str]]:
        cfg = self.profile
        warmup: list[str] = []

        direction_tf = cfg["timeframes"]["direction"]
        pullback_tf = cfg["timeframes"]["pullback"]
        trigger_tf = cfg["timeframes"]["trigger"]

        direction_history = self.history[direction_tf]
        pullback_history = self.history[pullback_tf]
        trigger_history = self.history[trigger_tf]

        metrics: dict[str, Any] = {
            "direction": {
                "timeframe": direction_tf,
                "ma": None,
                "ma_previous": None,
                "open_reference": None,
            },
            "pullback": {"timeframe": pullback_tf, "rsi": None, "z": None},
            "trigger": {"timeframe": trigger_tf, "rsi": None, "z": None},
            "filters": {"adx": None, "atr": None, "open_reference": None},
        }

        for label, timeframe, history in (
            ("direction", direction_tf, direction_history),
            ("pullback", pullback_tf, pullback_history),
            ("trigger", trigger_tf, trigger_history),
        ):
            if not history:
                warmup.append(f"{label}:{timeframe}:NO_BAR")

        direction_cfg = cfg["direction"]
        if direction_cfg["ma_enabled"] and direction_history:
            values = [_price(bar, direction_cfg["price_source"]) for bar in direction_history]
            period = direction_cfg["ma_period"]
            metrics["direction"]["ma"] = _moving_average(values, period, direction_cfg["ma_type"])
            if metrics["direction"]["ma"] is None:
                warmup.append(f"direction:{direction_tf}:MA{period}")
            if not direction_cfg["require_close_side"]:
                metrics["direction"]["ma_previous"] = _moving_average(values[:-1], period, direction_cfg["ma_type"])
                if metrics["direction"]["ma_previous"] is None:
                    warmup.append(f"direction:{direction_tf}:MA_PREVIOUS{period}")

        pullback_cfg = cfg["pullback"]
        if pullback_history:
            closes = [bar.close for bar in pullback_history]
            if pullback_cfg["rsi_enabled"]:
                metrics["pullback"]["rsi"] = _rsi(closes, pullback_cfg["rsi_period"])
                if metrics["pullback"]["rsi"] is None:
                    warmup.append(f"pullback:{pullback_tf}:RSI{pullback_cfg['rsi_period']}")
            if pullback_cfg["z_enabled"]:
                metrics["pullback"]["z"] = _zscore(closes, pullback_cfg["z_period"])
                if metrics["pullback"]["z"] is None:
                    warmup.append(f"pullback:{pullback_tf}:Z{pullback_cfg['z_period']}")

        trigger_cfg = cfg["trigger"]
        if trigger_history:
            closes = [bar.close for bar in trigger_history]
            if trigger_cfg["rsi_enabled"]:
                metrics["trigger"]["rsi"] = _rsi(closes, trigger_cfg["rsi_period"])
                if metrics["trigger"]["rsi"] is None:
                    warmup.append(f"trigger:{trigger_tf}:RSI{trigger_cfg['rsi_period']}")
            if trigger_cfg["z_enabled"]:
                metrics["trigger"]["z"] = _zscore(closes, trigger_cfg["z_period"])
                if metrics["trigger"]["z"] is None:
                    warmup.append(f"trigger:{trigger_tf}:Z{trigger_cfg['z_period']}")

        adx_cfg = cfg["filters"]["adx"]
        if adx_cfg["enabled"]:
            adx_history = self.history[adx_cfg["timeframe"]]
            metrics["filters"]["adx"] = _adx(adx_history, adx_cfg["period"])
            if metrics["filters"]["adx"] is None:
                warmup.append(f"filter:{adx_cfg['timeframe']}:ADX{adx_cfg['period']}")

        atr_cfg = cfg["filters"]["atr"]
        if atr_cfg["enabled"]:
            atr_history = self.history[atr_cfg["timeframe"]]
            metrics["filters"]["atr"] = _atr(atr_history, atr_cfg["period"])
            if metrics["filters"]["atr"] is None:
                warmup.append(f"filter:{atr_cfg['timeframe']}:ATR{atr_cfg['period']}")

        if direction_cfg["open_filter_enabled"]:
            reference = self._reference_open(direction_cfg["open_reference_mode"])
            metrics["direction"]["open_reference"] = reference
            if reference is None and direction_cfg["open_reference_mode"] != "NONE":
                warmup.append(f"direction:OPEN:{direction_cfg['open_reference_mode']}")

        open_cfg = cfg["filters"]["open"]
        if open_cfg["enabled"]:
            reference = self._reference_open(open_cfg["reference_mode"])
            metrics["filters"]["open_reference"] = reference
            if reference is None and open_cfg["reference_mode"] != "NONE":
                warmup.append(f"filter:OPEN:{open_cfg['reference_mode']}")

        return metrics, sorted(set(warmup))

    def _reference_open(self, mode: str) -> float | None:
        mode = mode.upper()
        if mode == "NONE":
            return None

        history = self.history["M1"]
        if not history:
            return None

        dated = [
            (datetime.fromtimestamp(bar.time, tz=timezone.utc), bar)
            for bar in history
        ]
        latest_dt = dated[-1][0]

        if mode == "DAILY_OPEN":
            for dt, bar in dated:
                if dt.date() == latest_dt.date() and dt.hour == 0 and dt.minute == 0:
                    return bar.open
            return None

        if mode == "PREVIOUS_DAY_OPEN":
            dates = sorted({dt.date() for dt, _ in dated if dt.date() < latest_dt.date()}, reverse=True)
            if not dates:
                return None
            previous = dates[0]
            for dt, bar in dated:
                if dt.date() == previous and dt.hour == 0 and dt.minute == 0:
                    return bar.open
            return None

        if mode == "SESSION_OPEN":
            sessions = self.profile["sessions"]
            current_minutes = latest_dt.hour * 60 + latest_dt.minute
            starts: list[int] = []
            for index in (1, 2):
                if not sessions[f"session{index}_enabled"]:
                    continue
                start_text = sessions[f"session{index}_start"]
                hour, minute = (int(part) for part in start_text.split(":"))
                start = hour * 60 + minute
                if start <= current_minutes:
                    starts.append(start)
            if not starts:
                return None
            target = max(starts)
            target_hour, target_minute = divmod(target, 60)
            for dt, bar in dated:
                if (
                    dt.date() == latest_dt.date()
                    and dt.hour == target_hour
                    and dt.minute == target_minute
                ):
                    return bar.open
            return None

        return None

    def status_payload(self, *, market_connected: bool) -> dict[str, Any]:
        state = self.state if market_connected else "STALE"
        blocked_reason = self.blocked_reason if market_connected else "BRIDGE_STALE"
        return {
            "available": market_connected,
            "ready": market_connected and self.state != "WARMUP",
            "state": state,
            "internal_state": self.state,
            "blocked_reason": blocked_reason,
            "profile_name": self.profile["profile"]["name"],
            "profile_hash": self.profile_hash,
            "symbol": self.profile["strategy"]["symbol"],
            "timeframes": deepcopy(self.profile["timeframes"]),
            "direction": self.direction,
            "armed_side": self.armed_side,
            "signal_sequence": self.signal_sequence,
            "last_signal": deepcopy(self.last_signal),
            "warmup_reasons": list(self.warmup_reasons),
            "bars_seen": {
                timeframe: len(self.history[timeframe])
                for timeframe in TIMEFRAME_OPTIONS
            },
            "indicators": deepcopy(self.last_metrics),
            "conditions": deepcopy(self.last_conditions),
            "last_data_error": self.last_data_error,
            "last_reset_reason": self.last_reset_reason,
            "last_evaluated_trigger_time": self._last_evaluated_trigger_time,
            "trading_enabled": False,
            "execution_enabled": False,
        }
