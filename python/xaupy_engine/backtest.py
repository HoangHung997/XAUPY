from __future__ import annotations

from copy import deepcopy
import csv
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from .config_schema import normalized_profile
from .journal import default_journal_directory
from .strategy_engine import Bar, StrategyDataError, StrategyEngine, _atr, _rsi, _zscore


TIMEFRAME_SECONDS: dict[str, int] = {
    "M1": 60,
    "M3": 180,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H2": 7200,
    "H4": 14400,
}
BACKTEST_MODEL = "M1_OHLC_PARITY_V1"
DATASET_SCHEMA_VERSION = 1
BACKTEST_SCHEMA_VERSION = 1


class BacktestError(ValueError):
    """Raised when Task 011 dataset/request/profile is unsupported or invalid."""


class BacktestCancelled(RuntimeError):
    """Raised when a long historical replay is cooperatively cancelled."""


def _raise_if_cancelled(
    cancel_check: Callable[[], bool] | None,
) -> None:
    if cancel_check is not None and cancel_check():
        raise BacktestCancelled("backtest cancelled")


def default_backtest_directory() -> Path:
    override = os.environ.get("XAUPY_BACKTEST_DIR")
    if override:
        return Path(override).expanduser()
    return default_journal_directory().parent / "backtests"


def _finite_number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise BacktestError(f"{name} must be numeric")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise BacktestError(f"{name} must be numeric") from exc
    if not math.isfinite(parsed):
        raise BacktestError(f"{name} must be finite")
    if positive and parsed <= 0:
        raise BacktestError(f"{name} must be positive")
    return parsed


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise BacktestError(f"{name} must be integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise BacktestError(f"{name} must be integer") from exc
    if parsed <= 0:
        raise BacktestError(f"{name} must be positive")
    return parsed


def _parse_timestamp(value: Any) -> int:
    if isinstance(value, bool):
        raise BacktestError("bar time must not be boolean")
    if isinstance(value, (int, float)):
        parsed = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise BacktestError("bar time is required")
        try:
            parsed = int(text)
        except ValueError:
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise BacktestError(
                    "bar time must be epoch seconds or ISO-8601"
                ) from exc
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            parsed = int(dt.timestamp())
    else:
        raise BacktestError("bar time must be epoch seconds or ISO-8601")

    if parsed <= 0:
        raise BacktestError("bar time must be positive")
    if parsed % 60 != 0:
        raise BacktestError("M1 bar time must align to a whole minute")
    return parsed


@dataclass(frozen=True)
class DatasetMetadata:
    symbol: str
    point_size: float
    tick_size: float
    tick_value: float
    volume_min: float
    volume_max: float
    volume_step: float
    timezone_offset_minutes: int

    def public(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "point_size": self.point_size,
            "tick_size": self.tick_size,
            "tick_value": self.tick_value,
            "volume_min": self.volume_min,
            "volume_max": self.volume_max,
            "volume_step": self.volume_step,
            "timezone_offset_minutes": self.timezone_offset_minutes,
        }


@dataclass(frozen=True)
class HistoricalDataset:
    path: Path
    fingerprint: str
    metadata: DatasetMetadata
    bars: tuple[Bar, ...]

    @property
    def first_time(self) -> int:
        return self.bars[0].time

    @property
    def last_time(self) -> int:
        return self.bars[-1].time

    def local_date(self, timestamp: int) -> date:
        offset = timezone(timedelta(minutes=self.metadata.timezone_offset_minutes))
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(offset).date()

    def inspect_payload(self) -> dict[str, Any]:
        return {
            "schema_version": DATASET_SCHEMA_VERSION,
            "path": str(self.path),
            "file_name": self.path.name,
            "dataset_fingerprint": self.fingerprint,
            "timeframe": "M1",
            "bar_count": len(self.bars),
            "first_time": self.first_time,
            "last_time": self.last_time,
            "first_date": self.local_date(self.first_time).isoformat(),
            "last_date": self.local_date(self.last_time).isoformat(),
            "metadata": self.metadata.public(),
        }


def load_historical_dataset(path_value: str | os.PathLike[str]) -> HistoricalDataset:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    if not path.is_file():
        raise BacktestError(f"historical dataset does not exist: {path}")

    raw_bytes = path.read_bytes()
    fingerprint = hashlib.sha256(raw_bytes).hexdigest()
    suffix = path.suffix.lower()

    if suffix == ".json":
        metadata, bars = _load_json_dataset(raw_bytes)
    elif suffix == ".csv":
        metadata, bars = _load_csv_dataset(raw_bytes)
    else:
        raise BacktestError("Task 011 dataset must be .json or .csv")

    _validate_bar_sequence(bars)
    return HistoricalDataset(
        path=path,
        fingerprint=fingerprint,
        metadata=metadata,
        bars=tuple(bars),
    )


def _load_json_dataset(raw_bytes: bytes) -> tuple[DatasetMetadata, list[Bar]]:
    try:
        payload = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BacktestError(f"invalid dataset JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BacktestError("dataset JSON root must be object")
    if payload.get("schema_version") != DATASET_SCHEMA_VERSION:
        raise BacktestError("dataset schema_version must be 1")
    if str(payload.get("timeframe", "")).upper() != "M1":
        raise BacktestError("Task 011 input timeframe must be M1")

    metadata = _metadata_from_mapping(payload)
    raw_bars = payload.get("bars")
    if not isinstance(raw_bars, list) or not raw_bars:
        raise BacktestError("dataset bars must be a non-empty array")

    bars: list[Bar] = []
    for index, raw in enumerate(raw_bars):
        if not isinstance(raw, dict):
            raise BacktestError(f"bars[{index}] must be object")
        try:
            bars.append(
                Bar.from_payload(
                    {
                        "time": _parse_timestamp(raw.get("time")),
                        "open": raw.get("open"),
                        "high": raw.get("high"),
                        "low": raw.get("low"),
                        "close": raw.get("close"),
                        "tick_volume": raw.get("tick_volume", 0),
                    }
                )
            )
        except StrategyDataError as exc:
            raise BacktestError(f"bars[{index}]: {exc}") from exc
    return metadata, bars


def _load_csv_dataset(raw_bytes: bytes) -> tuple[DatasetMetadata, list[Bar]]:
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BacktestError("dataset CSV must be UTF-8") from exc

    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise BacktestError("dataset CSV is missing header")

    required_bar = {"time", "open", "high", "low", "close"}
    required_meta = {
        "symbol",
        "point_size",
        "tick_size",
        "tick_value",
        "volume_min",
        "volume_max",
        "volume_step",
        "timezone_offset_minutes",
    }
    fields = {str(name).strip() for name in reader.fieldnames if name is not None}
    missing = sorted((required_bar | required_meta).difference(fields))
    if missing:
        raise BacktestError(f"dataset CSV missing columns: {missing}")

    rows = [row for row in reader if any(str(value or "").strip() for value in row.values())]
    if not rows:
        raise BacktestError("dataset CSV contains no bars")

    metadata = _metadata_from_mapping(rows[0])
    expected_meta = metadata.public()

    bars: list[Bar] = []
    for index, row in enumerate(rows):
        row_metadata = _metadata_from_mapping(row).public()
        if row_metadata != expected_meta:
            raise BacktestError(
                f"dataset CSV metadata changes at row {index + 2}"
            )
        try:
            bars.append(
                Bar.from_payload(
                    {
                        "time": _parse_timestamp(row.get("time")),
                        "open": row.get("open"),
                        "high": row.get("high"),
                        "low": row.get("low"),
                        "close": row.get("close"),
                        "tick_volume": row.get("tick_volume") or 0,
                    }
                )
            )
        except StrategyDataError as exc:
            raise BacktestError(f"CSV row {index + 2}: {exc}") from exc
    return metadata, bars


def _metadata_from_mapping(mapping: dict[str, Any]) -> DatasetMetadata:
    symbol = str(mapping.get("symbol", "")).strip()
    if not symbol:
        raise BacktestError("dataset symbol is required")

    point_size = _finite_number(mapping.get("point_size"), "point_size", positive=True)
    tick_size = _finite_number(mapping.get("tick_size"), "tick_size", positive=True)
    tick_value = _finite_number(mapping.get("tick_value"), "tick_value", positive=True)
    volume_min = _finite_number(mapping.get("volume_min"), "volume_min", positive=True)
    volume_max = _finite_number(mapping.get("volume_max"), "volume_max", positive=True)
    volume_step = _finite_number(mapping.get("volume_step"), "volume_step", positive=True)

    try:
        offset = int(mapping.get("timezone_offset_minutes", 0))
    except (TypeError, ValueError) as exc:
        raise BacktestError("timezone_offset_minutes must be integer") from exc
    if not -840 <= offset <= 840:
        raise BacktestError("timezone_offset_minutes must be between -840 and 840")
    if volume_max < volume_min:
        raise BacktestError("volume_max must be >= volume_min")
    if volume_step > volume_max:
        raise BacktestError("volume_step must be <= volume_max")

    return DatasetMetadata(
        symbol=symbol,
        point_size=point_size,
        tick_size=tick_size,
        tick_value=tick_value,
        volume_min=volume_min,
        volume_max=volume_max,
        volume_step=volume_step,
        timezone_offset_minutes=offset,
    )


def _validate_bar_sequence(bars: list[Bar]) -> None:
    if not bars:
        raise BacktestError("dataset has no bars")
    previous = 0
    for index, bar in enumerate(bars):
        if index > 0 and bar.time <= previous:
            raise BacktestError(
                "dataset M1 bars must be strictly increasing; "
                f"row {index + 1} time={bar.time} follows {previous}"
            )
        previous = bar.time


def aggregate_timeframe(
    m1_bars: tuple[Bar, ...] | list[Bar],
    timeframe: str,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> list[Bar]:
    timeframe = timeframe.upper()
    if timeframe not in TIMEFRAME_SECONDS:
        raise BacktestError(f"unsupported timeframe: {timeframe}")
    if timeframe == "M1":
        return list(m1_bars)

    seconds = TIMEFRAME_SECONDS[timeframe]
    expected_count = seconds // 60
    buckets: dict[int, list[Bar]] = {}

    for index, bar in enumerate(m1_bars):
        if index % 1024 == 0:
            _raise_if_cancelled(cancel_check)
        bucket = (bar.time // seconds) * seconds
        buckets.setdefault(bucket, []).append(bar)

    _raise_if_cancelled(cancel_check)
    result: list[Bar] = []
    for index, bucket in enumerate(sorted(buckets)):
        if index % 256 == 0:
            _raise_if_cancelled(cancel_check)
        bars = buckets[bucket]
        expected_times = [bucket + index * 60 for index in range(expected_count)]
        if len(bars) != expected_count:
            continue
        if [bar.time for bar in bars] != expected_times:
            continue

        result.append(
            Bar(
                time=bucket,
                open=bars[0].open,
                high=max(bar.high for bar in bars),
                low=min(bar.low for bar in bars),
                close=bars[-1].close,
                tick_volume=sum(bar.tick_volume for bar in bars),
            )
        )
    return result


def build_close_schedule(
    m1_bars: tuple[Bar, ...] | list[Bar],
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[int, dict[str, Bar]]:
    schedule: dict[int, dict[str, Bar]] = {}
    for timeframe, seconds in TIMEFRAME_SECONDS.items():
        _raise_if_cancelled(cancel_check)
        for bar in aggregate_timeframe(
            m1_bars,
            timeframe,
            cancel_check=cancel_check,
        ):
            schedule.setdefault(bar.time + seconds, {})[timeframe] = bar
    return schedule


@dataclass
class PendingStopEntry:
    signal_sequence: int
    signal_time: int
    detected_close_time: int
    side: str
    trigger_price: float
    created_time: int
    expires_at: int
    signal_stale_at: int
    profile_hash: str
    dataset_fingerprint: str
    signal_trigger_rsi: float | None = None
    signal_trigger_z: float | None = None


@dataclass
class OpenPosition:
    trade_id: int
    signal_sequence: int
    signal_time: int
    side: str
    entry_time: int
    entry_price: float
    volume: float
    sl: float
    tp: float
    original_sl: float
    original_risk: float
    profile_hash: str
    dataset_fingerprint: str
    initial_volume: float = 0.0
    original_tp: float = 0.0
    hard_tp: float = 0.0
    entry_mode: str = "MARKET"
    pending_trigger_price: float | None = None
    signal_trigger_rsi: float | None = None
    signal_trigger_z: float | None = None
    mfe_price_units: float = 0.0
    mae_price_units: float = 0.0
    breakeven_applied: bool = False
    partial_close_applied: bool = False
    partial_close_event: dict[str, Any] | None = None
    realized_gross: float = 0.0
    realized_commission: float = 0.0
    realized_net: float = 0.0
    trailing_updates: int = 0
    sl_tighten_updates: int = 0
    dynamic_extended: bool = False
    dynamic_extension_time: int | None = None
    dynamic_peak_rsi: float | None = None
    dynamic_peak_z: float | None = None
    dynamic_exit_pending: bool = False
    dynamic_exit_reason: str | None = None
    dynamic_lock_applied: bool = False


@dataclass
class BacktestState:
    balance: float
    positions: list[OpenPosition] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    pending_signals: list[dict[str, Any]] = field(default_factory=list)
    pending_entries: list[PendingStopEntry] = field(default_factory=list)
    pending_entry_events: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    drawdown_curve: list[dict[str, Any]] = field(default_factory=list)
    skipped_signals: dict[str, int] = field(default_factory=dict)
    trades_by_day: dict[str, int] = field(default_factory=dict)
    pnl_by_day: dict[str, float] = field(default_factory=dict)
    day_start_balance: dict[str, float] = field(default_factory=dict)
    consecutive_losses_by_day: dict[str, int] = field(default_factory=dict)
    last_exit_time: int | None = None
    next_trade_id: int = 1
    peak_equity: float = 0.0




class BacktestEngine:
    def __init__(
        self,
        profile: dict[str, Any],
        *,
        initial_balance: float,
        spread_pips: float,
        commission_per_lot: float,
    ) -> None:
        self.profile = normalized_profile(profile)
        self.initial_balance = _finite_number(
            initial_balance,
            "initial_balance",
            positive=True,
        )
        self.spread_pips = _finite_number(spread_pips, "spread_pips")
        self.commission_per_lot = _finite_number(
            commission_per_lot,
            "commission_per_lot",
        )
        if self.spread_pips < 0:
            raise BacktestError("spread_pips must be >= 0")
        if self.commission_per_lot < 0:
            raise BacktestError("commission_per_lot must be >= 0")

        self._validate_profile_support()

    def _validate_profile_support(self) -> None:
        unsupported: list[str] = []
        if self.profile["entry"]["mode"] not in {"MARKET", "STOP_CONFIRM"}:
            unsupported.append("entry.mode must be MARKET or STOP_CONFIRM")
        if self.profile["stop_loss"]["mode"] not in {"FIXED", "STRUCTURE", "ATR"}:
            unsupported.append("stop_loss.mode must be FIXED, STRUCTURE or ATR")
        if self.profile["take_profit"]["mode"] not in {"FIXED", "RR", "ZRSI_DYNAMIC"}:
            unsupported.append("take_profit.mode must be FIXED, RR or ZRSI_DYNAMIC")
        if (
            self.profile["management"]["sl_tighten_mode"] == "ZRSI_ASSIST"
            and self.profile["take_profit"]["mode"] != "ZRSI_DYNAMIC"
        ):
            unsupported.append("ZRSI_ASSIST requires take_profit.mode=ZRSI_DYNAMIC")
        if self.profile["news"]["enabled"]:
            unsupported.append("news.enabled requires historical news data unavailable in Task 013")
        timezone_mode = str(self.profile["sessions"]["timezone"]).upper()
        if timezone_mode not in {"BROKER", "UTC"}:
            unsupported.append("sessions.timezone must be BROKER or UTC in Task 013")
        if unsupported:
            raise BacktestError("; ".join(unsupported))

    def run(
        self,
        dataset: HistoricalDataset,
        *,
        from_date: str,
        to_date: str,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        _raise_if_cancelled(cancel_check)
        if dataset.metadata.symbol != self.profile["strategy"]["symbol"]:
            raise BacktestError(
                f"dataset symbol {dataset.metadata.symbol} does not match "
                f"profile symbol {self.profile['strategy']['symbol']}"
            )

        start_date = self._parse_date(from_date, "from_date")
        end_date = self._parse_date(to_date, "to_date")
        if end_date < start_date:
            raise BacktestError("to_date must be >= from_date")

        in_range: list[Bar] = []
        for index, bar in enumerate(dataset.bars):
            if index % 1024 == 0:
                _raise_if_cancelled(cancel_check)
            local_date = dataset.local_date(bar.time)
            if start_date <= local_date <= end_date:
                in_range.append(bar)
        if not in_range:
            raise BacktestError("requested date range contains no M1 bars")

        last_allowed_time = in_range[-1].time
        schedule = build_close_schedule(
            dataset.bars,
            cancel_check=cancel_check,
        )
        _raise_if_cancelled(cancel_check)
        strategy = StrategyEngine(self.profile, max_history=4096)
        state = BacktestState(
            balance=self.initial_balance,
            peak_equity=self.initial_balance,
        )
        last_signal_sequence = 0
        spread_price = self.spread_pips * dataset.metadata.point_size
        first_range_time = in_range[0].time

        process_bars: list[Bar] = []
        for index, bar in enumerate(dataset.bars):
            if index % 1024 == 0:
                _raise_if_cancelled(cancel_check)
            if bar.time > last_allowed_time:
                break
            process_bars.append(bar)

        range_setup_reset = False
        for bar in process_bars:
            _raise_if_cancelled(cancel_check)
            local_date = dataset.local_date(bar.time)
            allow_entries = start_date <= local_date <= end_date
            if allow_entries and not range_setup_reset:
                # Pre-range bars are indicator warm-up evidence only. A setup or
                # signal armed outside the requested sample must not leak into
                # the sample. Retain historical bars, but reset actionable
                # state exactly at the first in-range M1 bar.
                strategy.reset_setup("BACKTEST_RANGE_START")
                state.pending_signals.clear()
                last_signal_sequence = strategy.signal_sequence
                range_setup_reset = True
            if allow_entries:
                self._ensure_day_state(state, dataset, bar.time)

            if allow_entries and state.pending_signals:
                pending = list(state.pending_signals)
                state.pending_signals.clear()
                for signal in pending:
                    self._try_open_signal(
                        state,
                        strategy,
                        dataset,
                        bar,
                        signal,
                        spread_price,
                    )

            if allow_entries and state.pending_entries:
                self._process_pending_entries(
                    state,
                    strategy,
                    dataset,
                    bar,
                    spread_price,
                )

            self._process_positions(
                state,
                dataset,
                bar,
                spread_price,
            )

            close_time = bar.time + 60
            closing = schedule.get(close_time, {})
            if closing:
                status = strategy.ingest_snapshot(
                    {
                        "symbol": dataset.metadata.symbol,
                        "bars": {
                            timeframe: {
                                "time": closed.time,
                                "open": closed.open,
                                "high": closed.high,
                                "low": closed.low,
                                "close": closed.close,
                                "tick_volume": closed.tick_volume,
                            }
                            for timeframe, closed in closing.items()
                        },
                    }
                )

                self._observe_position_management(
                    state,
                    strategy,
                    dataset,
                    bar,
                    spread_price,
                )

                current_sequence = int(status.get("signal_sequence", 0))
                if current_sequence > last_signal_sequence:
                    signal = deepcopy(status.get("last_signal"))
                    if isinstance(signal, dict):
                        signal["detected_close_time"] = close_time
                        if allow_entries and close_time <= last_allowed_time + 60:
                            state.pending_signals.append(signal)
                    last_signal_sequence = current_sequence

            if bar.time >= first_range_time:
                self._append_curve_point(
                    state,
                    dataset,
                    bar,
                    spread_price,
                )

        _raise_if_cancelled(cancel_check)
        if state.pending_entries:
            final_time = in_range[-1].time + 60
            for pending in list(state.pending_entries):
                self._record_pending_event(
                    state,
                    pending,
                    "END_OF_DATA",
                    final_time,
                )
                self._skip(state, "PENDING_END_OF_DATA")
            state.pending_entries.clear()

        if state.positions:
            final_bar = in_range[-1]
            for position in list(state.positions):
                exit_price = (
                    final_bar.close
                    if position.side == "BUY"
                    else final_bar.close + spread_price
                )
                self._close_position(
                    state,
                    dataset,
                    position,
                    exit_time=final_bar.time + 60,
                    exit_price=exit_price,
                    reason="END_OF_DATA",
                )
            self._append_curve_point(
                state,
                dataset,
                final_bar,
                spread_price,
                replace_same_time=True,
            )

        return self._result_payload(
            state,
            strategy,
            dataset,
            start_date=start_date,
            end_date=end_date,
        )

    @staticmethod
    def _parse_date(value: str, name: str) -> date:
        try:
            return date.fromisoformat(str(value))
        except ValueError as exc:
            raise BacktestError(f"{name} must be YYYY-MM-DD") from exc

    def _try_open_signal(
        self,
        state: BacktestState,
        strategy: StrategyEngine,
        dataset: HistoricalDataset,
        bar: Bar,
        signal: dict[str, Any],
        spread_price: float,
    ) -> None:
        side = str(signal.get("side", "")).upper()
        detected_close_time = int(signal.get("detected_close_time", 0) or 0)
        max_age_seconds = int(self.profile["entry"]["max_signal_age_bars"]) * 60
        if (
            detected_close_time > 0
            and bar.time - detected_close_time > max_age_seconds
        ):
            self._skip(state, "SIGNAL_EXPIRED")
            return
        if side not in {"BUY", "SELL"}:
            self._skip(state, "INVALID_SIDE")
            return

        entry_mode = str(self.profile["entry"]["mode"]).upper()
        signal_rsi, signal_z = self._signal_trigger_metrics(signal, strategy)

        if entry_mode == "STOP_CONFIRM":
            if self.profile["entry"]["cancel_on_opposite_setup"]:
                opposite = "SELL" if side == "BUY" else "BUY"
                removed = [
                    item
                    for item in state.pending_entries
                    if item.side == opposite
                ]
                if removed:
                    state.pending_entries = [
                        item
                        for item in state.pending_entries
                        if item.side != opposite
                    ]
                    for item in removed:
                        self._record_pending_event(
                            state,
                            item,
                            "CANCEL_OPPOSITE_SETUP",
                            bar.time,
                        )
                        self._skip(state, "PENDING_CANCEL_OPPOSITE_SETUP")

            trigger_tf = str(self.profile["timeframes"]["trigger"])
            history = strategy.history[trigger_tf]
            if not history:
                self._skip(state, "STOP_CONFIRM_TRIGGER_WARMUP")
                return
            trigger_bar = history[-1]
            signal_time = int(signal.get("bar_time", 0) or 0)
            if signal_time and trigger_bar.time != signal_time:
                matching = [item for item in history if item.time == signal_time]
                if not matching:
                    self._skip(state, "STOP_CONFIRM_SIGNAL_BAR_MISSING")
                    return
                trigger_bar = matching[-1]

            buffer_value = float(self.profile["entry"]["pending_buffer_price_units"])
            trigger_price = (
                trigger_bar.high + spread_price + buffer_value
                if side == "BUY"
                else trigger_bar.low - buffer_value
            )
            expiration_seconds = (
                int(self.profile["entry"]["pending_expiration_minutes"]) * 60
            )
            expires_at = detected_close_time + expiration_seconds
            stale_at = detected_close_time + max_age_seconds
            if detected_close_time <= 0:
                detected_close_time = bar.time
                expires_at = bar.time + expiration_seconds
                stale_at = bar.time + max_age_seconds
            if bar.time >= min(expires_at, stale_at):
                self._skip(state, "PENDING_EXPIRED")
                return

            state.pending_entries = [
                item for item in state.pending_entries if item.side != side
            ]
            pending_entry = PendingStopEntry(
                signal_sequence=int(signal.get("sequence", 0)),
                signal_time=signal_time,
                detected_close_time=detected_close_time,
                side=side,
                trigger_price=trigger_price,
                created_time=bar.time,
                expires_at=expires_at,
                signal_stale_at=stale_at,
                profile_hash=str(
                    signal.get("profile_hash") or strategy.profile_hash
                ),
                dataset_fingerprint=dataset.fingerprint,
                signal_trigger_rsi=signal_rsi,
                signal_trigger_z=signal_z,
            )
            state.pending_entries.append(pending_entry)
            self._record_pending_event(
                state,
                pending_entry,
                "CREATED",
                bar.time,
            )
            return

        if len(state.positions) >= int(self.profile["risk"]["max_open_positions"]):
            self._skip(state, "MAX_OPEN_POSITIONS")
            return

        entry_price = bar.open + spread_price if side == "BUY" else bar.open
        self._open_position(
            state,
            strategy,
            dataset,
            bar,
            spread_price,
            side=side,
            entry_price=entry_price,
            signal_sequence=int(signal.get("sequence", 0)),
            signal_time=int(signal.get("bar_time", 0)),
            profile_hash=str(signal.get("profile_hash") or strategy.profile_hash),
            entry_mode="MARKET",
            pending_trigger_price=None,
            signal_trigger_rsi=signal_rsi,
            signal_trigger_z=signal_z,
        )

    def _process_pending_entries(
        self,
        state: BacktestState,
        strategy: StrategyEngine,
        dataset: HistoricalDataset,
        bar: Bar,
        spread_price: float,
    ) -> None:
        for pending in list(state.pending_entries):
            if bar.time >= pending.signal_stale_at:
                state.pending_entries.remove(pending)
                self._record_pending_event(
                    state,
                    pending,
                    "SIGNAL_EXPIRED",
                    bar.time,
                )
                self._skip(state, "PENDING_SIGNAL_EXPIRED")
                continue
            if bar.time >= pending.expires_at:
                state.pending_entries.remove(pending)
                self._record_pending_event(
                    state,
                    pending,
                    "EXPIRED",
                    bar.time,
                )
                self._skip(state, "PENDING_EXPIRED")
                continue

            if self.profile["entry"]["cancel_on_direction_change"]:
                direction = str(strategy.direction).upper()
                side_allowed = (
                    direction == pending.side
                    or direction == "BOTH"
                )
                if not side_allowed:
                    state.pending_entries.remove(pending)
                    self._record_pending_event(
                        state,
                        pending,
                        "CANCEL_DIRECTION_CHANGE",
                        bar.time,
                    )
                    self._skip(state, "PENDING_CANCEL_DIRECTION_CHANGE")
                    continue

            if pending.side == "BUY":
                executable_open = bar.open + spread_price
                executable_extreme = bar.high + spread_price
                triggered = executable_extreme >= pending.trigger_price
                fill_price = (
                    executable_open
                    if executable_open >= pending.trigger_price
                    else pending.trigger_price
                )
            else:
                executable_open = bar.open
                executable_extreme = bar.low
                triggered = executable_extreme <= pending.trigger_price
                fill_price = (
                    executable_open
                    if executable_open <= pending.trigger_price
                    else pending.trigger_price
                )

            if not triggered:
                continue

            state.pending_entries.remove(pending)
            self._record_pending_event(
                state,
                pending,
                "TRIGGERED",
                bar.time,
                fill_price=fill_price,
            )
            if len(state.positions) >= int(self.profile["risk"]["max_open_positions"]):
                self._skip(state, "PENDING_FILL_MAX_OPEN_POSITIONS")
                continue

            allowed, reason = self._entry_allowed(state, dataset, bar.time)
            if not allowed:
                self._skip(state, f"PENDING_FILL_{reason}")
                continue

            self._open_position(
                state,
                strategy,
                dataset,
                bar,
                spread_price,
                side=pending.side,
                entry_price=fill_price,
                signal_sequence=pending.signal_sequence,
                signal_time=pending.signal_time,
                profile_hash=pending.profile_hash,
                entry_mode="STOP_CONFIRM",
                pending_trigger_price=pending.trigger_price,
                signal_trigger_rsi=pending.signal_trigger_rsi,
                signal_trigger_z=pending.signal_trigger_z,
                entry_guard_already_checked=True,
            )

    def _open_position(
        self,
        state: BacktestState,
        strategy: StrategyEngine,
        dataset: HistoricalDataset,
        bar: Bar,
        spread_price: float,
        *,
        side: str,
        entry_price: float,
        signal_sequence: int,
        signal_time: int,
        profile_hash: str,
        entry_mode: str,
        pending_trigger_price: float | None,
        signal_trigger_rsi: float | None,
        signal_trigger_z: float | None,
        entry_guard_already_checked: bool = False,
    ) -> None:
        if not entry_guard_already_checked:
            allowed, reason = self._entry_allowed(state, dataset, bar.time)
            if not allowed:
                self._skip(state, reason)
                return

        try:
            sl, risk_distance = self._initial_stop(
                strategy,
                dataset,
                side,
                entry_price,
                spread_price,
            )
        except BacktestError as exc:
            if str(exc).startswith("not enough "):
                self._skip(state, "STOP_WARMUP")
                return
            raise

        original_tp, hard_tp = self._initial_targets(
            side,
            entry_price,
            risk_distance,
        )
        volume = self._position_volume(
            state.balance,
            dataset.metadata,
            risk_distance,
        )
        if volume is None:
            self._skip(state, "VOLUME_BELOW_MIN")
            return

        position = OpenPosition(
            trade_id=state.next_trade_id,
            signal_sequence=signal_sequence,
            signal_time=signal_time,
            side=side,
            entry_time=bar.time,
            entry_price=entry_price,
            volume=volume,
            sl=sl,
            tp=hard_tp,
            original_sl=sl,
            original_risk=risk_distance,
            profile_hash=profile_hash,
            dataset_fingerprint=dataset.fingerprint,
            initial_volume=volume,
            original_tp=original_tp,
            hard_tp=hard_tp,
            entry_mode=entry_mode,
            pending_trigger_price=pending_trigger_price,
            signal_trigger_rsi=signal_trigger_rsi,
            signal_trigger_z=signal_trigger_z,
        )
        state.next_trade_id += 1
        state.positions.append(position)

        day_key = self._day_key(dataset, bar.time)
        state.trades_by_day[day_key] = state.trades_by_day.get(day_key, 0) + 1

    def _signal_trigger_metrics(
        self,
        signal: dict[str, Any],
        strategy: StrategyEngine,
    ) -> tuple[float | None, float | None]:
        indicators = signal.get("indicators")
        trigger = (
            indicators.get("trigger")
            if isinstance(indicators, dict)
            else None
        )
        rsi = self._optional_number(
            trigger.get("rsi") if isinstance(trigger, dict) else None
        )
        z_value = self._optional_number(
            trigger.get("z") if isinstance(trigger, dict) else None
        )
        current_rsi, current_z = self._management_metrics(strategy)
        return (
            rsi if rsi is not None else current_rsi,
            z_value if z_value is not None else current_z,
        )

    def _management_metrics(
        self,
        strategy: StrategyEngine,
    ) -> tuple[float | None, float | None]:
        trigger_tf = str(self.profile["timeframes"]["trigger"])
        history = strategy.history[trigger_tf]
        closes = [item.close for item in history]
        rsi = _rsi(closes, int(self.profile["trigger"]["rsi_period"]))
        z_value = _zscore(closes, int(self.profile["trigger"]["z_period"]))
        return rsi, z_value

    @staticmethod
    def _optional_number(value: Any) -> float | None:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if math.isfinite(result) else None

    def _entry_allowed(
        self,
        state: BacktestState,
        dataset: HistoricalDataset,
        timestamp: int,
    ) -> tuple[bool, str]:
        day_key = self._day_key(dataset, timestamp)
        self._ensure_day_state(state, dataset, timestamp)

        risk = self.profile["risk"]
        if state.trades_by_day.get(day_key, 0) >= int(risk["max_trades_per_day"]):
            return False, "MAX_TRADES_PER_DAY"

        if state.consecutive_losses_by_day[day_key] >= int(risk["max_consecutive_losses"]):
            return False, "MAX_CONSECUTIVE_LOSSES"

        start_balance = state.day_start_balance[day_key]
        daily_pnl = state.pnl_by_day[day_key]
        if daily_pnl <= -(start_balance * float(risk["max_daily_loss_pct"]) / 100.0):
            return False, "MAX_DAILY_LOSS"

        if (
            risk["stop_after_daily_target"]
            and daily_pnl >= start_balance * float(risk["daily_target_pct"]) / 100.0
        ):
            return False, "DAILY_TARGET"

        cooldown = int(risk["cooldown_minutes"]) * 60
        if (
            cooldown > 0
            and state.last_exit_time is not None
            and timestamp - state.last_exit_time < cooldown
        ):
            return False, "COOLDOWN"

        if not self._session_allowed(dataset, timestamp):
            return False, "SESSION_FILTER"

        return True, "OK"

    def _ensure_day_state(
        self,
        state: BacktestState,
        dataset: HistoricalDataset,
        timestamp: int,
    ) -> None:
        day_key = self._day_key(dataset, timestamp)
        state.day_start_balance.setdefault(day_key, state.balance)
        state.pnl_by_day.setdefault(day_key, 0.0)
        state.consecutive_losses_by_day.setdefault(day_key, 0)

    def _session_allowed(
        self,
        dataset: HistoricalDataset,
        timestamp: int,
    ) -> bool:
        sessions = self.profile["sessions"]
        mode = str(sessions["timezone"]).upper()
        offset_minutes = (
            dataset.metadata.timezone_offset_minutes
            if mode == "BROKER"
            else 0
        )
        tz = timezone(timedelta(minutes=offset_minutes))
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(tz)

        weekday_key = (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )[dt.weekday()]
        if not sessions[weekday_key]:
            return False

        windows: list[tuple[int, int]] = []
        for index in (1, 2):
            if not sessions[f"session{index}_enabled"]:
                continue
            start = self._minutes(sessions[f"session{index}_start"])
            end = self._minutes(sessions[f"session{index}_end"])
            windows.append((start, end))

        if not windows:
            return True

        current = dt.hour * 60 + dt.minute
        for start, end in windows:
            if start == end:
                return True
            if start < end and start <= current < end:
                return True
            if start > end and (current >= start or current < end):
                return True
        return False

    @staticmethod
    def _minutes(value: str) -> int:
        hour, minute = (int(part) for part in str(value).split(":"))
        return hour * 60 + minute

    def _initial_stop(
        self,
        strategy: StrategyEngine,
        dataset: HistoricalDataset,
        side: str,
        entry_price: float,
        spread_price: float,
    ) -> tuple[float, float]:
        cfg = self.profile["stop_loss"]
        mode = cfg["mode"]
        if mode == "FIXED":
            distance = float(cfg["fixed_price_units"])
        elif mode == "STRUCTURE":
            timeframe = cfg["structure_timeframe"]
            lookback = int(cfg["structure_lookback"])
            history = strategy.history[timeframe]
            if len(history) < lookback:
                raise BacktestError(
                    f"not enough {timeframe} bars for structure stop lookback {lookback}"
                )
            window = history[-lookback:]
            buffer_value = float(cfg["structure_buffer_price_units"])
            if side == "BUY":
                raw_sl = min(item.low for item in window) - buffer_value
                distance = entry_price - raw_sl
            else:
                raw_sl = max(item.high for item in window) + buffer_value + spread_price
                distance = raw_sl - entry_price
        elif mode == "ATR":
            timeframe = str(cfg["atr_timeframe"])
            period = int(cfg["atr_period"])
            value = _atr(strategy.history[timeframe], period)
            if value is None:
                raise BacktestError(
                    f"not enough {timeframe} bars for ATR stop period {period}"
                )
            distance = value * float(cfg["atr_multiplier"])
        else:
            raise BacktestError(f"unsupported stop mode: {mode}")

        minimum = float(cfg["min_price_units"])
        maximum = float(cfg["max_price_units"])
        distance = max(minimum, min(maximum, distance))
        if not math.isfinite(distance) or distance <= 0:
            raise BacktestError("calculated stop distance is invalid")

        sl = entry_price - distance if side == "BUY" else entry_price + distance
        return sl, distance

    def _initial_targets(
        self,
        side: str,
        entry_price: float,
        risk_distance: float,
    ) -> tuple[float, float]:
        cfg = self.profile["take_profit"]
        mode = str(cfg["mode"])
        if mode == "FIXED":
            original_distance = float(cfg["fixed_price_units"])
            hard_distance = original_distance
        elif mode == "RR":
            original_distance = risk_distance * float(cfg["rr_ratio"])
            hard_distance = original_distance
        elif mode == "ZRSI_DYNAMIC":
            original_distance = float(cfg["fixed_price_units"])
            dynamic = cfg["dynamic"]
            hard_distance = (
                original_distance
                + float(dynamic["max_extension_price_units"])
            )
            if dynamic["emergency_server_tp_enabled"]:
                emergency_distance = float(
                    dynamic["emergency_server_tp_price_units"]
                )
                hard_distance = min(hard_distance, emergency_distance)
            hard_distance = max(original_distance, hard_distance)
        else:
            raise BacktestError(f"unsupported TP mode: {mode}")

        original_tp = (
            entry_price + original_distance
            if side == "BUY"
            else entry_price - original_distance
        )
        hard_tp = (
            entry_price + hard_distance
            if side == "BUY"
            else entry_price - hard_distance
        )
        return original_tp, hard_tp

    def _initial_target(
        self,
        side: str,
        entry_price: float,
        risk_distance: float,
    ) -> float:
        original_tp, _ = self._initial_targets(
            side,
            entry_price,
            risk_distance,
        )
        return original_tp

    def _position_volume(
        self,
        balance: float,
        metadata: DatasetMetadata,
        risk_distance: float,
    ) -> float | None:
        risk = self.profile["risk"]
        if risk["sizing_mode"] == "FIXED_LOT":
            raw = float(risk["fixed_lot"])
        else:
            risk_amount = balance * float(risk["risk_percent"]) / 100.0
            risk_per_lot = (
                risk_distance / metadata.tick_size * metadata.tick_value
            )
            if risk_per_lot <= 0:
                return None
            raw = risk_amount / risk_per_lot

        maximum = min(float(risk["max_lot"]), metadata.volume_max)
        raw = min(raw, maximum)
        steps = math.floor((raw + 1e-12) / metadata.volume_step)
        volume = round(steps * metadata.volume_step, 10)
        if volume < metadata.volume_min - 1e-12:
            return None
        return volume

    def _process_positions(
        self,
        state: BacktestState,
        dataset: HistoricalDataset,
        bar: Bar,
        spread_price: float,
    ) -> None:
        dynamic_mode = self.profile["take_profit"]["mode"] == "ZRSI_DYNAMIC"
        max_extension_seconds = (
            int(self.profile["take_profit"]["dynamic"]["max_extension_minutes"]) * 60
        )

        for position in list(state.positions):
            if position.side == "BUY":
                executable_open = bar.open
                executable_high = bar.high
                executable_low = bar.low
                favorable = max(0.0, executable_high - position.entry_price)
                adverse = max(0.0, position.entry_price - executable_low)
                gap_sl = executable_open <= position.sl
                touch_sl = executable_low <= position.sl
            else:
                executable_open = bar.open + spread_price
                executable_high = bar.high + spread_price
                executable_low = bar.low + spread_price
                favorable = max(0.0, position.entry_price - executable_low)
                adverse = max(0.0, executable_high - position.entry_price)
                gap_sl = executable_open >= position.sl
                touch_sl = executable_high >= position.sl

            position.mfe_price_units = max(position.mfe_price_units, favorable)
            position.mae_price_units = max(position.mae_price_units, adverse)

            target = (
                position.hard_tp
                if dynamic_mode and position.dynamic_extended
                else position.original_tp
            )
            if position.side == "BUY":
                gap_tp = executable_open >= target
                touch_tp = executable_high >= target
            else:
                gap_tp = executable_open <= target
                touch_tp = executable_low <= target

            exit_price: float | None = None
            reason: str | None = None

            if gap_sl:
                exit_price = executable_open
                reason = "SL_GAP"
            elif (
                dynamic_mode
                and position.dynamic_extended
                and position.dynamic_exit_pending
            ):
                exit_price = executable_open
                reason = position.dynamic_exit_reason or "ZRSI_REVERSAL"
            elif (
                dynamic_mode
                and position.dynamic_extended
                and position.dynamic_extension_time is not None
                and bar.time - position.dynamic_extension_time
                >= max_extension_seconds
            ):
                exit_price = executable_open
                reason = "DYNAMIC_MAX_TIME"
            elif gap_tp:
                exit_price = executable_open
                reason = (
                    "DYNAMIC_HARD_TP_GAP"
                    if dynamic_mode and position.dynamic_extended
                    else "TP_GAP"
                )
            elif touch_sl and touch_tp:
                exit_price = position.sl
                reason = "SL_AMBIGUOUS"
            elif touch_sl:
                exit_price = position.sl
                reason = "SL"
            elif touch_tp:
                exit_price = target
                reason = (
                    "DYNAMIC_HARD_TP"
                    if dynamic_mode and position.dynamic_extended
                    else "TP"
                )

            if exit_price is not None and reason is not None:
                self._close_position(
                    state,
                    dataset,
                    position,
                    exit_time=bar.time + 60,
                    exit_price=exit_price,
                    reason=reason,
                )
                continue

            management = self.profile["management"]
            if (
                management["breakeven_enabled"]
                and not position.breakeven_applied
                and position.mfe_price_units
                >= position.original_risk * float(management["breakeven_trigger_rr"])
            ):
                offset = float(management["breakeven_offset_price_units"])
                new_sl = (
                    position.entry_price + offset
                    if position.side == "BUY"
                    else position.entry_price - offset
                )
                if self._improves_stop(position, new_sl):
                    position.sl = new_sl
                    position.breakeven_applied = True

    def _observe_position_management(
        self,
        state: BacktestState,
        strategy: StrategyEngine,
        dataset: HistoricalDataset,
        bar: Bar,
        spread_price: float,
    ) -> None:
        if not state.positions:
            return

        management = self.profile["management"]
        tp_cfg = self.profile["take_profit"]
        dynamic_cfg = tp_cfg["dynamic"]
        current_rsi, current_z = self._management_metrics(strategy)

        for position in list(state.positions):
            if position not in state.positions:
                continue

            if tp_cfg["mode"] == "ZRSI_DYNAMIC":
                original_distance = abs(position.original_tp - position.entry_price)
                near_distance = max(
                    0.0,
                    original_distance - float(dynamic_cfg["near_tp_distance"]),
                )
                if (
                    not position.dynamic_extended
                    and position.mfe_price_units >= near_distance
                    and self._continuation_strong(
                        position,
                        current_rsi,
                        current_z,
                    )
                ):
                    position.dynamic_extended = True
                    position.dynamic_extension_time = bar.time + 60
                    position.dynamic_peak_rsi = current_rsi
                    position.dynamic_peak_z = current_z

                if position.dynamic_extended:
                    if self._dynamic_reversal(
                        position,
                        current_rsi,
                        current_z,
                    ):
                        position.dynamic_exit_pending = True
                        position.dynamic_exit_reason = "ZRSI_REVERSAL"

                    if (
                        dynamic_cfg["lock_sl_at_original_tp"]
                        and not position.dynamic_lock_applied
                        and position.mfe_price_units
                        >= original_distance
                        + float(dynamic_cfg["lock_profit_buffer"])
                    ):
                        buffer_value = float(dynamic_cfg["lock_profit_buffer"])
                        candidate = (
                            position.original_tp + buffer_value
                            if position.side == "BUY"
                            else position.original_tp - buffer_value
                        )
                        current_exit = (
                            bar.close
                            if position.side == "BUY"
                            else bar.close + spread_price
                        )
                        if self._candidate_inside_market(
                            position.side,
                            candidate,
                            current_exit,
                        ) and self._apply_stop_candidate(
                            position,
                            candidate,
                            minimum_step=0.0,
                        ):
                            position.dynamic_lock_applied = True

            if (
                management["partial_close_enabled"]
                and not position.partial_close_applied
                and position.mfe_price_units
                >= position.original_risk
                * float(management["partial_close_at_rr"])
            ):
                self._apply_partial_close(
                    state,
                    dataset,
                    position,
                    bar,
                    spread_price,
                )

            if position not in state.positions:
                continue

            current_exit = (
                bar.close
                if position.side == "BUY"
                else bar.close + spread_price
            )

            if management["trailing_enabled"]:
                candidate = self._trailing_candidate(
                    strategy,
                    position,
                    current_exit,
                    spread_price,
                )
                if (
                    candidate is not None
                    and self._candidate_inside_market(
                        position.side,
                        candidate,
                        current_exit,
                    )
                    and self._apply_stop_candidate(
                        position,
                        candidate,
                        minimum_step=float(
                            management["trailing_step_price_units"]
                        ),
                    )
                ):
                    position.trailing_updates += 1

            tighten_mode = str(management["sl_tighten_mode"])
            candidate = self._tighten_candidate(
                strategy,
                position,
                current_exit,
                spread_price,
                tighten_mode,
            )
            if (
                candidate is not None
                and self._candidate_inside_market(
                    position.side,
                    candidate,
                    current_exit,
                )
                and self._apply_stop_candidate(
                    position,
                    candidate,
                    minimum_step=0.0,
                )
            ):
                position.sl_tighten_updates += 1

    def _continuation_strong(
        self,
        position: OpenPosition,
        current_rsi: float | None,
        current_z: float | None,
    ) -> bool:
        cfg = self.profile["take_profit"]["dynamic"]
        conditions: list[bool] = []

        if cfg["extend_use_z"]:
            if current_z is None or position.signal_trigger_z is None:
                return False
            conditions.append(
                current_z > position.signal_trigger_z
                if position.side == "BUY"
                else current_z < position.signal_trigger_z
            )
        if cfg["extend_use_rsi"]:
            if current_rsi is None or position.signal_trigger_rsi is None:
                return False
            conditions.append(
                current_rsi > position.signal_trigger_rsi
                if position.side == "BUY"
                else current_rsi < position.signal_trigger_rsi
            )

        if not conditions:
            return False
        return (
            all(conditions)
            if cfg["extend_logic"] == "BOTH"
            else any(conditions)
        )

    def _dynamic_reversal(
        self,
        position: OpenPosition,
        current_rsi: float | None,
        current_z: float | None,
    ) -> bool:
        cfg = self.profile["take_profit"]["dynamic"]
        conditions: list[bool] = []

        if cfg["extend_use_z"]:
            if current_z is None:
                return False
            if position.dynamic_peak_z is None:
                position.dynamic_peak_z = current_z
            if position.side == "BUY":
                position.dynamic_peak_z = max(position.dynamic_peak_z, current_z)
                conditions.append(
                    position.dynamic_peak_z - current_z
                    >= float(cfg["exit_z_reverse_delta"])
                )
            else:
                position.dynamic_peak_z = min(position.dynamic_peak_z, current_z)
                conditions.append(
                    current_z - position.dynamic_peak_z
                    >= float(cfg["exit_z_reverse_delta"])
                )

        if cfg["extend_use_rsi"]:
            if current_rsi is None:
                return False
            if position.dynamic_peak_rsi is None:
                position.dynamic_peak_rsi = current_rsi
            if position.side == "BUY":
                position.dynamic_peak_rsi = max(
                    position.dynamic_peak_rsi,
                    current_rsi,
                )
                conditions.append(
                    position.dynamic_peak_rsi - current_rsi
                    >= float(cfg["exit_rsi_reverse_delta"])
                )
            else:
                position.dynamic_peak_rsi = min(
                    position.dynamic_peak_rsi,
                    current_rsi,
                )
                conditions.append(
                    current_rsi - position.dynamic_peak_rsi
                    >= float(cfg["exit_rsi_reverse_delta"])
                )

        if not conditions:
            return False
        return (
            all(conditions)
            if cfg["extend_logic"] == "BOTH"
            else any(conditions)
        )

    def _trailing_candidate(
        self,
        strategy: StrategyEngine,
        position: OpenPosition,
        current_exit: float,
        spread_price: float,
    ) -> float | None:
        management = self.profile["management"]
        mode = str(management["trailing_mode"])
        if mode == "STRUCTURE":
            return self._structure_stop_candidate(
                strategy,
                position.side,
                int(management["trailing_structure_lookback"]),
                spread_price,
            )
        if mode == "ATR":
            return self._atr_stop_candidate(
                strategy,
                position.side,
                current_exit,
                float(management["trailing_atr_multiplier"]),
            )
        return None

    def _tighten_candidate(
        self,
        strategy: StrategyEngine,
        position: OpenPosition,
        current_exit: float,
        spread_price: float,
        mode: str,
    ) -> float | None:
        if mode == "OFF":
            return None
        if mode == "STRUCTURE":
            return self._structure_stop_candidate(
                strategy,
                position.side,
                int(self.profile["stop_loss"]["structure_lookback"]),
                spread_price,
            )
        if mode == "ATR":
            return self._atr_stop_candidate(
                strategy,
                position.side,
                current_exit,
                float(self.profile["stop_loss"]["atr_multiplier"]),
            )
        if mode == "ZRSI_ASSIST" and position.dynamic_extended:
            buffer_value = float(
                self.profile["take_profit"]["dynamic"]["lock_profit_buffer"]
            )
            return (
                position.original_tp + buffer_value
                if position.side == "BUY"
                else position.original_tp - buffer_value
            )
        return None

    def _structure_stop_candidate(
        self,
        strategy: StrategyEngine,
        side: str,
        lookback: int,
        spread_price: float,
    ) -> float | None:
        timeframe = str(self.profile["stop_loss"]["structure_timeframe"])
        history = strategy.history[timeframe]
        if lookback <= 0 or len(history) < lookback:
            return None
        window = history[-lookback:]
        buffer_value = float(
            self.profile["stop_loss"]["structure_buffer_price_units"]
        )
        if side == "BUY":
            return min(item.low for item in window) - buffer_value
        return max(item.high for item in window) + buffer_value + spread_price

    def _atr_stop_candidate(
        self,
        strategy: StrategyEngine,
        side: str,
        current_exit: float,
        multiplier: float,
    ) -> float | None:
        cfg = self.profile["stop_loss"]
        timeframe = str(cfg["atr_timeframe"])
        value = _atr(strategy.history[timeframe], int(cfg["atr_period"]))
        if value is None:
            return None
        distance = value * multiplier
        return (
            current_exit - distance
            if side == "BUY"
            else current_exit + distance
        )

    @staticmethod
    def _candidate_inside_market(
        side: str,
        candidate: float,
        current_exit: float,
    ) -> bool:
        if side == "BUY":
            return candidate < current_exit - 1e-12
        return candidate > current_exit + 1e-12

    @staticmethod
    def _improves_stop(
        position: OpenPosition,
        candidate: float,
    ) -> bool:
        if position.side == "BUY":
            return candidate > position.sl + 1e-12
        return candidate < position.sl - 1e-12

    def _apply_stop_candidate(
        self,
        position: OpenPosition,
        candidate: float,
        *,
        minimum_step: float,
    ) -> bool:
        if not math.isfinite(candidate):
            return False
        improvement = (
            candidate - position.sl
            if position.side == "BUY"
            else position.sl - candidate
        )
        if improvement <= 1e-12:
            return False
        if improvement + 1e-12 < max(0.0, minimum_step):
            return False
        position.sl = candidate
        return True

    def _apply_partial_close(
        self,
        state: BacktestState,
        dataset: HistoricalDataset,
        position: OpenPosition,
        bar: Bar,
        spread_price: float,
    ) -> None:
        percent = float(self.profile["management"]["partial_close_percent"])
        step = dataset.metadata.volume_step
        minimum = dataset.metadata.volume_min
        raw_close = position.volume * percent / 100.0
        steps = math.floor((raw_close + 1e-12) / step)
        close_volume = round(steps * step, 10)
        remaining = round(position.volume - close_volume, 10)
        if (
            close_volume < minimum - 1e-12
            or remaining < minimum - 1e-12
        ):
            return

        exit_price = (
            bar.close
            if position.side == "BUY"
            else bar.close + spread_price
        )
        move = (
            exit_price - position.entry_price
            if position.side == "BUY"
            else position.entry_price - exit_price
        )
        gross = (
            move
            / dataset.metadata.tick_size
            * dataset.metadata.tick_value
            * close_volume
        )
        commission = self.commission_per_lot * close_volume
        net = gross - commission

        state.balance += net
        day_key = self._day_key(dataset, bar.time)
        state.pnl_by_day[day_key] = state.pnl_by_day.get(day_key, 0.0) + net

        position.realized_gross += gross
        position.realized_commission += commission
        position.realized_net += net
        position.volume = remaining
        position.partial_close_applied = True
        position.partial_close_event = {
            "time": bar.time + 60,
            "price": self._round(exit_price),
            "percent": self._round(percent),
            "volume": self._round(close_volume),
            "remaining_volume": self._round(remaining),
            "gross_pl": self._round(gross),
            "commission": self._round(commission),
            "net_pl": self._round(net),
        }

    def _close_position(
        self,
        state: BacktestState,
        dataset: HistoricalDataset,
        position: OpenPosition,
        *,
        exit_time: int,
        exit_price: float,
        reason: str,
    ) -> None:
        final_close_volume = position.volume
        price_move = (
            exit_price - position.entry_price
            if position.side == "BUY"
            else position.entry_price - exit_price
        )
        final_gross = (
            price_move
            / dataset.metadata.tick_size
            * dataset.metadata.tick_value
            * final_close_volume
        )
        final_commission = self.commission_per_lot * final_close_volume
        final_net = final_gross - final_commission
        gross = position.realized_gross + final_gross
        commission = position.realized_commission + final_commission
        net = position.realized_net + final_net
        state.balance += final_net

        duration_seconds = max(0, exit_time - position.entry_time)
        day_key = self._day_key(dataset, exit_time - 1)
        state.pnl_by_day[day_key] = state.pnl_by_day.get(day_key, 0.0) + final_net
        if net < 0:
            state.consecutive_losses_by_day[day_key] = (
                state.consecutive_losses_by_day.get(day_key, 0) + 1
            )
        else:
            state.consecutive_losses_by_day[day_key] = 0

        state.last_exit_time = exit_time
        if position in state.positions:
            state.positions.remove(position)

        state.trades.append(
            {
                "trade_id": position.trade_id,
                "signal_sequence": position.signal_sequence,
                "signal_time": position.signal_time,
                "side": position.side,
                "entry_mode": position.entry_mode,
                "pending_trigger_price": (
                    self._round(position.pending_trigger_price)
                    if position.pending_trigger_price is not None
                    else None
                ),
                "entry_time": position.entry_time,
                "exit_time": exit_time,
                "entry_price": self._round(position.entry_price),
                "exit_price": self._round(exit_price),
                "volume": self._round(position.initial_volume),
                "final_close_volume": self._round(final_close_volume),
                "original_sl": self._round(position.original_sl),
                "final_sl": self._round(position.sl),
                "original_tp": self._round(position.original_tp),
                "hard_tp": self._round(position.hard_tp),
                "tp": self._round(position.tp),
                "breakeven_applied": position.breakeven_applied,
                "partial_close_applied": position.partial_close_applied,
                "partial_close": deepcopy(position.partial_close_event),
                "trailing_updates": position.trailing_updates,
                "sl_tighten_updates": position.sl_tighten_updates,
                "dynamic_extended": position.dynamic_extended,
                "dynamic_extension_time": position.dynamic_extension_time,
                "dynamic_lock_applied": position.dynamic_lock_applied,
                "gross_pl": self._round(gross),
                "commission": self._round(commission),
                "net_pl": self._round(net),
                "duration_seconds": duration_seconds,
                "exit_reason": reason,
                "mae_price_units": self._round(position.mae_price_units),
                "mfe_price_units": self._round(position.mfe_price_units),
                "mae_usd": self._round(
                    position.mae_price_units
                    / dataset.metadata.tick_size
                    * dataset.metadata.tick_value
                    * position.initial_volume
                ),
                "mfe_usd": self._round(
                    position.mfe_price_units
                    / dataset.metadata.tick_size
                    * dataset.metadata.tick_value
                    * position.initial_volume
                ),
                "profile_hash": position.profile_hash,
                "dataset_fingerprint": position.dataset_fingerprint,
            }
        )

    def _append_curve_point(
        self,
        state: BacktestState,
        dataset: HistoricalDataset,
        bar: Bar,
        spread_price: float,
        *,
        replace_same_time: bool = False,
    ) -> None:
        unrealized = 0.0
        for position in state.positions:
            exit_price = (
                bar.close
                if position.side == "BUY"
                else bar.close + spread_price
            )
            move = (
                exit_price - position.entry_price
                if position.side == "BUY"
                else position.entry_price - exit_price
            )
            unrealized += (
                move
                / dataset.metadata.tick_size
                * dataset.metadata.tick_value
                * position.volume
            )

        equity = state.balance + unrealized
        point = {
            "time": bar.time + 60,
            "balance": self._round(state.balance),
            "equity": self._round(equity),
        }
        if (
            replace_same_time
            and state.equity_curve
            and state.equity_curve[-1]["time"] == point["time"]
        ):
            state.equity_curve[-1] = point
        else:
            state.equity_curve.append(point)

        state.peak_equity = max(state.peak_equity, equity)
        dd_usd = max(0.0, state.peak_equity - equity)
        dd_pct = (
            0.0
            if state.peak_equity <= 0
            else dd_usd / state.peak_equity * 100.0
        )
        drawdown = {
            "time": point["time"],
            "drawdown_usd": self._round(dd_usd),
            "drawdown_pct": self._round(dd_pct),
        }
        if (
            replace_same_time
            and state.drawdown_curve
            and state.drawdown_curve[-1]["time"] == drawdown["time"]
        ):
            state.drawdown_curve[-1] = drawdown
        else:
            state.drawdown_curve.append(drawdown)

    def _result_payload(
        self,
        state: BacktestState,
        strategy: StrategyEngine,
        dataset: HistoricalDataset,
        *,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        wins = [trade for trade in state.trades if trade["net_pl"] > 0]
        losses = [trade for trade in state.trades if trade["net_pl"] < 0]
        gross_profit = sum(float(trade["net_pl"]) for trade in wins)
        gross_loss = sum(float(trade["net_pl"]) for trade in losses)
        total = len(state.trades)
        net_profit = state.balance - self.initial_balance
        max_dd_usd = max(
            (float(point["drawdown_usd"]) for point in state.drawdown_curve),
            default=0.0,
        )
        max_dd_pct = max(
            (float(point["drawdown_pct"]) for point in state.drawdown_curve),
            default=0.0,
        )

        metrics = {
            "net_profit": self._round(net_profit),
            "net_profit_pct": self._round(
                net_profit / self.initial_balance * 100.0
            ),
            "gross_profit": self._round(gross_profit),
            "gross_loss": self._round(gross_loss),
            "profit_factor": (
                self._round(gross_profit / abs(gross_loss))
                if gross_loss < 0
                else None
            ),
            "total_trades": total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": self._round(len(wins) / total * 100.0) if total else 0.0,
            "average_trade": self._round(net_profit / total) if total else 0.0,
            "max_drawdown_usd": self._round(max_dd_usd),
            "max_drawdown_pct": self._round(max_dd_pct),
            "initial_balance": self._round(self.initial_balance),
            "final_balance": self._round(state.balance),
            "final_equity": self._round(state.balance),
        }

        deterministic = {
            "schema_version": BACKTEST_SCHEMA_VERSION,
            "model": BACKTEST_MODEL,
            "engine_profile_hash": strategy.profile_hash,
            "dataset_fingerprint": dataset.fingerprint,
            "dataset_metadata": dataset.metadata.public(),
            "from_date": start_date.isoformat(),
            "to_date": end_date.isoformat(),
            "initial_balance": self._round(self.initial_balance),
            "spread_pips": self._round(self.spread_pips),
            "commission_per_lot": self._round(self.commission_per_lot),
            "profile": deepcopy(self.profile),
            "metrics": metrics,
            "skipped_signals": dict(sorted(state.skipped_signals.items())),
            "pending_entry_events": deepcopy(state.pending_entry_events),
            "equity_curve": self._downsample_curve(state.equity_curve),
            "drawdown_curve": self._downsample_curve(state.drawdown_curve),
            "trades": state.trades,
        }
        encoded = json.dumps(
            deterministic,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        result_hash = hashlib.sha256(encoded).hexdigest()

        return {
            **deterministic,
            "result_hash": result_hash,
            "dataset_file_name": dataset.path.name,
        }

    def _record_pending_event(
        self,
        state: BacktestState,
        pending: PendingStopEntry,
        event: str,
        timestamp: int,
        *,
        fill_price: float | None = None,
    ) -> None:
        state.pending_entry_events.append(
            {
                "event": event,
                "time": int(timestamp),
                "signal_sequence": pending.signal_sequence,
                "signal_time": pending.signal_time,
                "side": pending.side,
                "trigger_price": self._round(pending.trigger_price),
                "fill_price": (
                    self._round(fill_price)
                    if fill_price is not None
                    else None
                ),
                "expires_at": pending.expires_at,
                "signal_stale_at": pending.signal_stale_at,
            }
        )

    @staticmethod
    def _skip(state: BacktestState, reason: str) -> None:
        state.skipped_signals[reason] = state.skipped_signals.get(reason, 0) + 1

    def _day_key(self, dataset: HistoricalDataset, timestamp: int) -> str:
        sessions = self.profile["sessions"]
        offset = (
            dataset.metadata.timezone_offset_minutes
            if str(sessions["timezone"]).upper() == "BROKER"
            else 0
        )
        tz = timezone(timedelta(minutes=offset))
        return (
            datetime.fromtimestamp(timestamp, tz=timezone.utc)
            .astimezone(tz)
            .date()
            .isoformat()
        )

    @staticmethod
    def _downsample_curve(
        points: list[dict[str, Any]],
        max_points: int = 1200,
    ) -> list[dict[str, Any]]:
        if len(points) <= max_points:
            return deepcopy(points)
        if max_points < 2:
            return [deepcopy(points[-1])]

        selected: list[dict[str, Any]] = []
        last_index = -1
        for step in range(max_points):
            index = round(step * (len(points) - 1) / (max_points - 1))
            if index == last_index:
                continue
            selected.append(deepcopy(points[index]))
            last_index = index
        return selected

    @staticmethod
    def _round(value: float) -> float:
        return round(float(value), 8)


class BacktestRepository:
    def __init__(self, root_dir: str | os.PathLike[str] | None = None) -> None:
        self.root_dir = (
            Path(root_dir).expanduser()
            if root_dir is not None
            else default_backtest_directory()
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
        return deepcopy(stored)

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise BacktestError("history limit must be 1..500")

        results: list[dict[str, Any]] = []
        for path in self.root_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            metrics = payload.get("metrics")
            if not isinstance(metrics, dict):
                continue
            results.append(
                {
                    "run_id": payload.get("run_id"),
                    "created_at_utc": payload.get("created_at_utc"),
                    "symbol": payload.get("dataset_metadata", {}).get("symbol"),
                    "model": payload.get("model"),
                    "from_date": payload.get("from_date"),
                    "to_date": payload.get("to_date"),
                    "dataset_file_name": payload.get("dataset_file_name"),
                    "dataset_fingerprint": payload.get("dataset_fingerprint"),
                    "result_hash": payload.get("result_hash"),
                    "profile_hash": payload.get("engine_profile_hash"),
                    "metrics": deepcopy(metrics),
                }
            )

        results.sort(
            key=lambda item: str(item.get("created_at_utc") or ""),
            reverse=True,
        )
        return results[:limit]

    def get(self, run_id: str) -> dict[str, Any]:
        path = self._run_path(run_id)
        if not path.is_file():
            raise BacktestError("backtest result does not exist")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BacktestError("stored backtest result is corrupt") from exc
        if not isinstance(payload, dict):
            raise BacktestError("stored backtest result root is invalid")
        return payload

    def delete(self, run_id: str) -> bool:
        path = self._run_path(run_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _run_path(self, run_id: str) -> Path:
        text = str(run_id).strip()
        try:
            parsed = UUID(text)
        except ValueError as exc:
            raise BacktestError("run_id must be UUID") from exc
        return self.root_dir / f"{parsed}.json"
