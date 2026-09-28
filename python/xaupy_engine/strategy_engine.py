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


HISTORY_LIMIT = 256
HISTORY_TIMEFRAME_SECONDS = {
    "M1": 60, "M3": 180, "M5": 300, "M15": 900,
    "M30": 1800, "H1": 3600, "H2": 7200, "H4": 14400,
}


def validated_bar_history(payload: dict[str, Any]) -> dict[str, list[Bar]]:
    """Validate optional MT5 closed history atomically, never infer a tick path."""
    if "bar_history" not in payload:
        return {}
    raw_history = payload["bar_history"]
    if not isinstance(raw_history, dict) or set(raw_history).difference(TIMEFRAME_OPTIONS):
        raise StrategyDataError("bar_history must contain only supported timeframes")
    server_time = payload.get("server_time")
    if isinstance(server_time, bool) or not isinstance(server_time, int) or server_time <= 0:
        raise StrategyDataError("bar_history requires positive integer MT5 server_time")
    latest = payload.get("bars")
    if not isinstance(latest, dict):
        raise StrategyDataError("bar_history requires latest closed bars")
    result: dict[str, list[Bar]] = {}
    for timeframe, rows in raw_history.items():
        if not isinstance(rows, list) or len(rows) > HISTORY_LIMIT:
            raise StrategyDataError(f"bar_history.{timeframe} must contain at most {HISTORY_LIMIT} bars")
        validated: list[Bar] = []
        for raw in rows:
            if not isinstance(raw, dict) or isinstance(raw.get("time"), bool) or not isinstance(raw.get("time"), int):
                raise StrategyDataError(f"bar_history.{timeframe} requires integer bar timestamps")
            bar = Bar.from_payload(raw)
            if validated and bar.time <= validated[-1].time:
                raise StrategyDataError(f"bar_history.{timeframe} timestamps must strictly increase")
            if bar.time + HISTORY_TIMEFRAME_SECONDS[timeframe] > server_time:
                raise StrategyDataError(f"bar_history.{timeframe} includes an unclosed/future bar")
            validated.append(bar)
        if validated:
            raw_latest = latest.get(timeframe)
            if not isinstance(raw_latest, dict):
                raise StrategyDataError(f"bar_history.{timeframe} has no latest closed bar")
            latest_bar = Bar.from_payload(raw_latest)
            if latest_bar.time + HISTORY_TIMEFRAME_SECONDS[timeframe] > server_time:
                raise StrategyDataError(f"bar_history.{timeframe} latest bar is not closed")
            if validated[-1].time > latest_bar.time:
                raise StrategyDataError(f"bar_history.{timeframe} is newer than latest closed bar")
            if validated[-1].time == latest_bar.time and validated[-1] != latest_bar:
                raise StrategyDataError(f"bar_history.{timeframe} disagrees with latest closed bar")
        result[timeframe] = validated
    return result


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


def _rsi_state(values: list[float], period: int) -> tuple[float, float] | None:
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

    return average_gain, average_loss


def _rsi_value(average_gain: float, average_loss: float) -> float:
    if average_loss == 0.0:
        if average_gain == 0.0:
            return 50.0
        return 100.0

    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _rsi(values: list[float], period: int) -> float | None:
    state = _rsi_state(values, period)
    return None if state is None else _rsi_value(*state)


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
        self.history_bootstrap_total = 0
        self.last_signal: dict[str, Any] | None = None
        self.last_metrics: dict[str, Any] = {}
        self.last_conditions: dict[str, Any] = {}
        self.warmup_reasons: list[str] = []
        self.blocked_reason: str | None = "NO_MARKET_DATA"
        self.last_data_error: str | None = None
        self.last_reset_reason: str | None = None
        self._last_evaluated_trigger_time: int | None = None
        self._observed_ticks_total = 0

        self.set_profile(profile or default_profile(), retain_history=False)

    def set_profile(self, profile: dict[str, Any], *, retain_history: bool = True) -> None:
        normalized = normalized_profile(profile)
        if self.profile and self.profile["strategy"]["symbol"] != normalized["strategy"]["symbol"]:
            retain_history = False
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
        self._reset_tick_observation()

    def _reset_tick_observation(self) -> None:
        self._tick_stream_id: str | None = None
        self._tick_sequence: int | None = None
        self._tick_last_time_msc: int | None = None
        self._tick_bar_times: dict[str, int] = {}
        self._tick_latch_bar_time: int | None = None
        self._tick_latches: dict[str, dict[str, bool]] = {}
        self._tick_candidate_extremes: dict[str, dict[str, float]] = {}
        self._tick_setup_latches: dict[str, Any] = {}
        self._tick_bar_extremes: dict[str, dict[str, Any]] = {}
        self._tick_reason: str | None = "WAIT_TICK_BASELINE"
        self._tick_required_closed_times: dict[str, int] = {}
        self._tick_metrics_cache_key: int | None = None
        self._tick_metrics_cache: tuple[Any, ...] | None = None
        self._display_metrics: dict[str, Any] = {}
        self._display_warmup: list[str] = []
        self._display_bars: dict[str, dict[str, Any]] = {}
        self._display_quote: dict[str, Any] = {}
        self._display_continuous = False
        self._display_reason = "WAIT_TICK_BASELINE"
        self._display_observed_ticks = 0

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
        self._tick_metrics_cache_key = None

        new_timeframes: set[str] = set()
        errors: list[str] = []

        # History is warm-up evidence, never replayed as historical trade signals.
        # Only initial/backfilled/gapped history resets setup. Repeated full
        # snapshots must not reset a current live setup every refresh.
        for timeframe, incoming in validated_bar_history(payload).items():
            if not incoming:
                continue
            current = self.history[timeframe]
            needs_bootstrap = (
                not current
                or incoming[0].time < current[0].time
                or incoming[-1].time > current[-1].time + HISTORY_TIMEFRAME_SECONDS[timeframe]
            )
            if needs_bootstrap:
                combined = {bar.time: bar for bar in current}
                combined.update({bar.time: bar for bar in incoming})
                self.history[timeframe] = [combined[t] for t in sorted(combined)][-self.max_history:]
                new_timeframes.add(timeframe)
        if new_timeframes:
            self.reset_setup("HISTORY_BOOTSTRAP")
            self.history_bootstrap_total += 1

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
        if new_timeframes and self.profile["trigger"]["confirm_closed_bar"]:
            self._evaluate(new_timeframes)
        elif new_timeframes and self._tick_last_time_msc is None:
            self.last_metrics, self.warmup_reasons = self._metrics()
            self.state = "WARMUP" if self.warmup_reasons else "WAIT_INTRABAR"
            self.blocked_reason = "WARMUP" if self.warmup_reasons else "WAIT_TICK_BASELINE"

        return self.status_payload(market_connected=True)

    def ingest_tick_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Consume actual ordered observations, never reconstruct an OHLC tick path.

        A new/discontinuous stream is baseline-only. Sequence numbers make retries
        idempotent while equal-millisecond ticks retain their supplied ordering.
        Closed history is filtered at each event time before indicator evaluation.
        """
        closed_confirmation = self.profile["trigger"]["confirm_closed_bar"]
        if not isinstance(payload, dict) or payload.get("symbol") != self.profile["strategy"]["symbol"]:
            raise StrategyDataError("tick batch symbol does not match active profile")
        batch = payload.get("tick_batch")
        if not isinstance(batch, dict):
            raise StrategyDataError("tick_batch must be an object")
        stream_id, sequence, complete = batch.get("stream_id"), batch.get("sequence"), batch.get("complete")
        if not isinstance(stream_id, str) or not stream_id or len(stream_id) > 128:
            raise StrategyDataError("tick_batch.stream_id must be a nonempty string <= 128 characters")
        if type(sequence) is not int or sequence < 1 or type(complete) is not bool:
            raise StrategyDataError("tick batch requires positive sequence and boolean complete")
        raw_ticks = batch.get("ticks")
        if not isinstance(raw_ticks, list) or len(raw_ticks) > 1000:
            raise StrategyDataError("tick_batch.ticks must contain at most 1000 observations")
        ticks: list[tuple[int, float | None, float | None]] = []
        for row in raw_ticks:
            if not isinstance(row, dict):
                raise StrategyDataError("tick observation must be an object")
            timestamp, bid, ask = row.get("time_msc"), row.get("bid"), row.get("ask")
            if type(timestamp) is not int or timestamp <= 0:
                raise StrategyDataError("tick time_msc must be a positive integer")
            if (type(bid) not in (int, float) or type(ask) not in (int, float)
                    or not math.isfinite(bid) or not math.isfinite(ask) or bid < 0 or ask < 0
                    or (bid > 0 and ask > 0 and bid > ask)):
                raise StrategyDataError("tick bid/ask must be finite nonnegative ordered quotes")
            if ticks and timestamp < ticks[-1][0]:
                raise StrategyDataError("ticks must preserve chronological order")
            valid_quote = bid > 0 and ask > 0
            ticks.append((timestamp, float(bid) if valid_quote else None, float(ask) if valid_quote else None))

        same_stream = stream_id == self._tick_stream_id
        if same_stream and self._tick_sequence is not None and sequence <= self._tick_sequence:
            return self.status_payload(market_connected=True)
        discontinuity = (
            not same_stream or not complete
            or (self._tick_sequence is not None and sequence != self._tick_sequence + 1)
            or (ticks and self._tick_last_time_msc is not None and ticks[0][0] < self._tick_last_time_msc)
        )
        if discontinuity:
            reason = "TICK_STREAM_BASELINE" if not same_stream else "TICK_STREAM_GAP"
            if closed_confirmation:
                # Display transport must never reset a setup that the user has
                # configured to confirm from closed bars.
                self._reset_tick_observation()
            else:
                self.reset_setup(reason)
            self._tick_stream_id, self._tick_sequence = stream_id, sequence
            self._tick_last_time_msc = ticks[-1][0] if ticks else None
            self._tick_reason = reason
            if ticks:
                self._tick_bar_times = self._tick_times(ticks[-1][0])
            for timestamp, bid, ask in ticks:
                if bid is not None:
                    self._update_tick_display(timestamp, bid, ask, continuous=False, reason=reason)
            if not closed_confirmation:
                self.last_metrics, self.warmup_reasons = self._metrics()
                self.state = "WARMUP" if self.warmup_reasons else "WAIT_INTRABAR"
            return self.status_payload(market_connected=True)

        self._tick_sequence = sequence
        self._display_continuous = complete
        for timestamp, bid, ask in ticks:
            if bid is None:
                # CopyTicks may include trade-only records without a valid
                # quote. Keep transport ordering but never invent its bid.
                self._tick_last_time_msc = timestamp
                continue
            bar_times = self._tick_times(timestamp)
            trigger_tf = self.profile["timeframes"]["trigger"]
            previous_trigger = self._tick_bar_times.get(trigger_tf)
            trigger_time = bar_times[trigger_tf]
            if (self._tick_last_time_msc is None or
                    (previous_trigger is not None and trigger_time > previous_trigger + HISTORY_TIMEFRAME_SECONDS[trigger_tf])):
                if not closed_confirmation:
                    self._clear_arm("TICK_BAR_GAP")
                self._tick_latches.clear()
                self._tick_candidate_extremes.clear()
                self._tick_setup_latches.clear()
                self._tick_latch_bar_time = None
                self._tick_bar_extremes.clear()
                self._tick_required_closed_times.clear()
                self._tick_reason = "TICK_BAR_GAP"
                self._display_bars.clear()
                self._update_tick_display(timestamp, bid, ask, continuous=False, reason="TICK_BAR_GAP")
            else:
                for tf, current_time in bar_times.items():
                    previous_time = self._tick_bar_times.get(tf)
                    if previous_time is not None and current_time > previous_time:
                        self._tick_required_closed_times[tf] = previous_time
                if not closed_confirmation:
                    self._evaluate_tick(timestamp, bid, bar_times)
                self._update_tick_display(timestamp, bid, ask, continuous=True, reason="OBSERVED_TICK",
                                          decision_projection=None if closed_confirmation else (self.last_metrics, self.warmup_reasons))
                self._observed_ticks_total += 1
            self._tick_last_time_msc = timestamp
            self._tick_bar_times = bar_times
        return self.status_payload(market_connected=True)

    def _update_tick_display(self, timestamp: int, bid: float, ask: float, *, continuous: bool, reason: str,
                             decision_projection: tuple[dict[str, Any], list[str]] | None = None) -> None:
        """Project observed forming-bar values without changing decision state.

        These OHLC ranges cover only ticks actually received since the baseline,
        so they remain explicitly partial. No current_bars/high-low payload is
        used to infer observations before a tick's timestamp.
        """
        if decision_projection is None:
            metrics, warmup, _ = self._tick_metrics(timestamp, bid)
        else:
            metrics, warmup = deepcopy(decision_projection[0]), list(decision_projection[1])
        # Indicator switches control entry logic, not whether a gauge can show
        # a mathematical value. Use configured periods for disabled gauges too.
        for role in ("pullback", "trigger"):
            cfg, timeframe = self.profile[role], self.profile["timeframes"][role]
            values, rsi_state = self._tick_metrics_cache[3][role]
            for name in ("rsi", "z"):
                if cfg[f"{name}_enabled"]:
                    continue
                period = cfg[f"{name}_period"]
                if name == "rsi" and rsi_state is not None:
                    gain, loss = rsi_state
                    change = bid - values[-1]
                    value = _rsi_value((gain * (period - 1) + max(change, 0)) / period,
                                       (loss * (period - 1) + max(-change, 0)) / period)
                else:
                    value = _rsi(values + [bid], period) if name == "rsi" else _zscore(values[-(period - 1):] + [bid], period)
                metrics[role][name] = value
                if value is None:
                    warmup.append(f"display:{role}:{timeframe}:{name.upper()}{period}")
        # A missing just-closed candle must not masquerade as a current RSI/Z.
        # Keep unrelated timeframes readable and expose the missing dependency.
        for role in ("pullback", "trigger"):
            timeframe = self.profile["timeframes"][role]
            if f"history:{timeframe}:CLOSED_BAR_PENDING" in warmup:
                metrics[role]["rsi"] = metrics[role]["z"] = None
        self._display_metrics, self._display_warmup = metrics, warmup
        self._display_quote = {"tick_time_msc": timestamp, "bid": bid, "ask": ask}
        self._display_continuous, self._display_reason = continuous, "WARMUP" if warmup else reason
        self._display_observed_ticks += 1
        for timeframe, seconds in HISTORY_TIMEFRAME_SECONDS.items():
            bar_time = (timestamp // 1000 // seconds) * seconds
            bar = self._display_bars.get(timeframe)
            if bar is None or bar["time"] != bar_time:
                self._display_bars[timeframe] = {"time": bar_time, "open": bid, "high": bid, "low": bid,
                    "close": bid, "observed_ticks": 1, "partial": True, "source": "OBSERVED_TICKS"}
            else:
                bar["high"], bar["low"], bar["close"] = max(bar["high"], bid), min(bar["low"], bid), bid
                bar["observed_ticks"] += 1

    def _tick_times(self, timestamp: int) -> dict[str, int]:
        seconds = timestamp // 1000
        return {tf: seconds // span * span for tf, span in HISTORY_TIMEFRAME_SECONDS.items()}

    def _tick_metrics(self, timestamp: int, bid: float) -> tuple[dict[str, Any], list[str], dict[str, list[Bar]]]:
        seconds = timestamp // 1000
        key = seconds // 60
        if self._tick_metrics_cache_key != key:
            closed = {tf: [bar for bar in bars if bar.time + HISTORY_TIMEFRAME_SECONDS[tf] <= seconds]
                      for tf, bars in self.history.items()}
            base_metrics, base_warmup = self._metrics(closed)
            role_state = {}
            for role in ("pullback", "trigger"):
                cfg, timeframe = self.profile[role], self.profile["timeframes"][role]
                values = [bar.close for bar in closed[timeframe]]
                state = _rsi_state(values, cfg["rsi_period"])
                role_state[role] = (values, state)
            self._tick_metrics_cache = closed, base_metrics, base_warmup, role_state
            self._tick_metrics_cache_key = key
        closed, base_metrics, base_warmup, role_state = self._tick_metrics_cache
        metrics, warmup = deepcopy(base_metrics), list(base_warmup)
        # Forming-bar indicators use a single current bid appended to CLOSED
        # closes, not one appended close per tick, and not the bar's future close.
        warmup = [reason for reason in warmup if not reason.startswith(("pullback:", "trigger:"))]
        for role in ("pullback", "trigger"):
            cfg, timeframe = self.profile[role], self.profile["timeframes"][role]
            values, rsi_state = role_state[role]
            for name, calculate in (("rsi", _rsi), ("z", _zscore)):
                if cfg[f"{name}_enabled"]:
                    period = cfg[f"{name}_period"]
                    if name == "rsi" and rsi_state is not None:
                        # Advance Wilder state once from the preceding CLOSED
                        # bar, never once per tick. O(1) even after long uptime.
                        change = bid - values[-1]
                        gain, loss = rsi_state
                        value = _rsi_value((gain * (period - 1) + max(change, 0)) / period,
                                           (loss * (period - 1) + max(-change, 0)) / period)
                    else:
                        prefix = values if name == "rsi" else values[-(period - 1):]
                        value = calculate(prefix + [bid], period)
                    metrics[role][name] = value
                    if value is None:
                        warmup.append(f"{role}:{timeframe}:{name.upper()}{cfg[f'{name}_period']}")
        required = set(self.profile["timeframes"].values())
        for gate in ("adx", "atr"):
            if self.profile["filters"][gate]["enabled"]:
                required.add(self.profile["filters"][gate]["timeframe"])
        for tf in required:
            expected = self._tick_required_closed_times.get(tf)
            if expected is not None and (not closed[tf] or closed[tf][-1].time < expected):
                warmup.append(f"history:{tf}:CLOSED_BAR_PENDING")
        return metrics, sorted(set(warmup)), closed

    def _evaluate_tick(self, timestamp: int, bid: float, bar_times: dict[str, int]) -> None:
        metrics, warmup, closed = self._tick_metrics(timestamp, bid)
        self.last_metrics, self.warmup_reasons = metrics, warmup
        if warmup:
            self._clear_arm("WARMUP")
            self.state, self._tick_reason = "WARMUP", "WARMUP"
            self._tick_latches.clear()
            self._tick_candidate_extremes.clear()
            self._tick_setup_latches.clear()
            return
        sides, label, reason = self._direction_sides(metrics, closed)
        self.direction = label
        if reason is not None or not sides:
            self._clear_arm(reason or "DIRECTION_NEUTRAL")
            self.state = "FILTER_BLOCKED" if reason else "WAIT_DIRECTION"
            self._tick_reason = reason or "DIRECTION_NEUTRAL"
            self._tick_latches.clear()
            self._tick_candidate_extremes.clear()
            self._tick_setup_latches.clear()
            return
        if self.armed_side is not None and self.armed_side not in sides:
            self._clear_arm("DIRECTION_CHANGED")
            self._tick_latches.clear()
            self._tick_candidate_extremes.clear()
            self._tick_setup_latches.clear()

        # Partial AND evidence is also directional, even before a setup arms.
        # A side becoming eligible again must accumulate fresh observations.
        for pending_side in set(self._tick_latches) | set(self._tick_candidate_extremes):
            if pending_side not in sides:
                self._tick_latches.pop(pending_side, None)
                self._tick_candidate_extremes.pop(pending_side, None)

        for role in ("pullback", "trigger"):
            timeframe = self.profile["timeframes"][role]
            extrema = self._tick_bar_extremes.setdefault(role, {})
            if extrema.get("bar_time") != bar_times[timeframe]:
                extrema.clear()
                extrema["bar_time"] = bar_times[timeframe]
            for indicator in ("rsi", "z"):
                value = metrics[role].get(indicator)
                if value is not None:
                    observed = extrema.setdefault(indicator, {"min": value, "max": value})
                    observed["min"], observed["max"] = min(observed["min"], value), max(observed["max"], value)

        pullback_time = bar_times[self.profile["timeframes"]["pullback"]]
        if self._tick_latch_bar_time != pullback_time:
            self._tick_latch_bar_time = pullback_time
            self._tick_latches.clear()
            self._tick_candidate_extremes.clear()
        cfg = self.profile["pullback"]
        for side in sorted(sides):
            latched = self._tick_latches.setdefault(side, {})
            extremes = self._tick_candidate_extremes.setdefault(side, {})
            for indicator in ("rsi", "z"):
                if cfg[f"{indicator}_enabled"]:
                    current = metrics["pullback"][indicator]
                    level = cfg[f"{indicator}_{side.lower()}_level"]
                    hit = current <= level if side == "BUY" else current >= level
                    latched[indicator] = latched.get(indicator, False) or hit
                current_trigger = metrics["trigger"].get(indicator)
                if current_trigger is not None:
                    previous = extremes.get(indicator, current_trigger)
                    extremes[indicator] = min(previous, current_trigger) if side == "BUY" else max(previous, current_trigger)

        self.last_conditions["pullback"] = {
            side: _logic(list(self._tick_latches[side].values()), cfg["logic"]) for side in sorted(sides)
        }
        if self.state.startswith("TRIGGERED_"):
            if not self._pullback_pass(self.armed_side, metrics):
                self._clear_arm("PULLBACK_RESET")
                self._tick_latches.clear()
                self._tick_candidate_extremes.clear()
                self._tick_setup_latches.clear()
            else:
                self.blocked_reason = "WAIT_PULLBACK_RESET"
            return
        trigger_time = bar_times[self.profile["timeframes"]["trigger"]]
        if self.armed_side is None:
            candidates = [side for side in sorted(sides) if self.last_conditions["pullback"][side]]
            if len(candidates) != 1:
                self.state = "AMBIGUOUS" if candidates else f"WAIT_PULLBACK_{label}"
                self.blocked_reason = "BOTH_SIDES_VALID" if candidates else "WAIT_PULLBACK"
                return
            side = candidates[0]
            self.armed_side, self._armed_trigger_time = side, trigger_time
            extrema = self._tick_candidate_extremes[side]
            self._trigger_rsi_extreme, self._trigger_z_extreme = extrema.get("rsi"), extrema.get("z")
            self._tick_setup_latches = {"side": side, "bar_time": pullback_time,
                                       "conditions": deepcopy(self._tick_latches[side])}
            self.state, self.blocked_reason = f"ARMED_{side}", "WAIT_NEXT_TRIGGER_BAR"
            self._tick_reason = "THRESHOLD_LATCHED"
            return

        age = (trigger_time - self._armed_trigger_time) // HISTORY_TIMEFRAME_SECONDS[self.profile["timeframes"]["trigger"]]
        if age > self.profile["entry"]["max_signal_age_bars"]:
            self._clear_arm("INTRABAR_SETUP_EXPIRED")
            self._tick_latches.clear()
            self._tick_candidate_extremes.clear()
            self._tick_setup_latches.clear()
            self._tick_reason = "INTRABAR_SETUP_EXPIRED"
            return
        self._update_trigger_extremes(self.armed_side, metrics)
        passed, details = self._trigger_pass(self.armed_side, metrics)
        details["confirmation_mode"] = "OBSERVED_TICKS_NEXT_BAR"
        self.last_conditions["trigger"] = details
        if trigger_time <= self._armed_trigger_time:
            self.blocked_reason = "WAIT_NEXT_TRIGGER_BAR"
            return
        self._last_evaluated_trigger_time = trigger_time
        if not passed:
            self.state, self.blocked_reason = f"ARMED_{self.armed_side}", "WAIT_TRIGGER_REVERSAL"
            return
        self.signal_sequence += 1
        self.state, self.blocked_reason = f"TRIGGERED_{self.armed_side}", None
        self._tick_reason = "OBSERVED_REVERSAL_CONFIRMED"
        self.last_signal = {
            "sequence": self.signal_sequence, "side": self.armed_side, "bar_time": trigger_time,
            "tick_time_msc": timestamp, "observation_mode": "OBSERVED_TICKS_NEXT_BAR",
            "tick_stream_id": self._tick_stream_id, "tick_batch_sequence": self._tick_sequence,
            "profile_hash": self.profile_hash, "direction": self.direction,
            "timeframes": deepcopy(self.profile["timeframes"]), "indicators": deepcopy(metrics),
            "threshold_latches": deepcopy(self._tick_setup_latches), "trigger": deepcopy(details),
        }

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
            passed = move + 1e-12 >= cfg["rsi_reversal_delta"]
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
            passed = move + 1e-12 >= cfg["z_reversal_delta"]
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
        histories: dict[str, list[Bar]] | None = None,
    ) -> tuple[set[str], str, str | None]:
        cfg = self.profile
        direction_cfg = cfg["direction"]
        direction_bar = (self.history if histories is None else histories)[cfg["timeframes"]["direction"]][-1]

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

    def _metrics(self, histories: dict[str, list[Bar]] | None = None) -> tuple[dict[str, Any], list[str]]:
        cfg = self.profile
        histories = self.history if histories is None else histories
        warmup: list[str] = []

        direction_tf = cfg["timeframes"]["direction"]
        pullback_tf = cfg["timeframes"]["pullback"]
        trigger_tf = cfg["timeframes"]["trigger"]

        direction_history = histories[direction_tf]
        pullback_history = histories[pullback_tf]
        trigger_history = histories[trigger_tf]

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
            adx_history = histories[adx_cfg["timeframe"]]
            metrics["filters"]["adx"] = _adx(adx_history, adx_cfg["period"])
            if metrics["filters"]["adx"] is None:
                warmup.append(f"filter:{adx_cfg['timeframe']}:ADX{adx_cfg['period']}")

        atr_cfg = cfg["filters"]["atr"]
        if atr_cfg["enabled"]:
            atr_history = histories[atr_cfg["timeframe"]]
            metrics["filters"]["atr"] = _atr(atr_history, atr_cfg["period"])
            if metrics["filters"]["atr"] is None:
                warmup.append(f"filter:{atr_cfg['timeframe']}:ATR{atr_cfg['period']}")

        if direction_cfg["open_filter_enabled"]:
            reference = self._reference_open(direction_cfg["open_reference_mode"], histories)
            metrics["direction"]["open_reference"] = reference
            if reference is None and direction_cfg["open_reference_mode"] != "NONE":
                warmup.append(f"direction:OPEN:{direction_cfg['open_reference_mode']}")

        open_cfg = cfg["filters"]["open"]
        if open_cfg["enabled"]:
            reference = self._reference_open(open_cfg["reference_mode"], histories)
            metrics["filters"]["open_reference"] = reference
            if reference is None and open_cfg["reference_mode"] != "NONE":
                warmup.append(f"filter:OPEN:{open_cfg['reference_mode']}")

        return metrics, sorted(set(warmup))

    def _reference_open(self, mode: str, histories: dict[str, list[Bar]] | None = None) -> float | None:
        mode = mode.upper()
        if mode == "NONE":
            return None

        history = (self.history if histories is None else histories)["M1"]
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
            "history_bootstrap_total": self.history_bootstrap_total,
            "last_signal": deepcopy(self.last_signal),
            "warmup_reasons": list(self.warmup_reasons),
            "bars_seen": {
                timeframe: len(self.history[timeframe])
                for timeframe in TIMEFRAME_OPTIONS
            },
            "indicators": deepcopy(self.last_metrics),
            "display": {
                "available": market_connected and bool(self._display_quote),
                "indicators_ready": market_connected and bool(self._display_quote) and not self._display_warmup,
                "observation_mode": "OBSERVED_TICKS",
                "confirmation_mode": "CLOSED_BAR" if self.profile["trigger"]["confirm_closed_bar"] else "OBSERVED_TICKS_NEXT_BAR",
                "stream_id": self._tick_stream_id,
                "sequence": self._tick_sequence,
                "continuous": market_connected and self._display_continuous,
                "reason": self._display_reason if market_connected else "BRIDGE_STALE",
                "observed_ticks": self._display_observed_ticks,
                **deepcopy(self._display_quote),
                "indicators": deepcopy(self._display_metrics) if market_connected else {},
                "warmup_reasons": list(self._display_warmup),
                "indicator_basis": {"direction": "CLOSED_BAR", "pullback": "FORMING_BAR_BID",
                                    "trigger": "FORMING_BAR_BID", "filters": "CLOSED_BAR"},
                "current_bars": deepcopy(self._display_bars) if market_connected else {},
            },
            "conditions": deepcopy(self.last_conditions),
            "last_data_error": self.last_data_error,
            "last_reset_reason": self.last_reset_reason,
            "last_evaluated_trigger_time": self._last_evaluated_trigger_time,
            "intrabar": {
                "mode": "CLOSED_BAR" if self.profile["trigger"]["confirm_closed_bar"] else "OBSERVED_TICKS_NEXT_BAR",
                "stream_id": self._tick_stream_id,
                "last_sequence": self._tick_sequence,
                "last_tick_time_msc": self._tick_last_time_msc,
                "observed_ticks": self._observed_ticks_total,
                "current_bar_times": deepcopy(self._tick_bar_times),
                "threshold_latches": deepcopy(self._tick_latches),
                "setup_latches": deepcopy(self._tick_setup_latches),
                "bar_extremes": deepcopy(self._tick_bar_extremes),
                "setup_extremes": {"rsi": self._trigger_rsi_extreme, "z": self._trigger_z_extreme},
                "reason": self._tick_reason,
            },
            "trading_enabled": False,
            "execution_enabled": False,
        }
