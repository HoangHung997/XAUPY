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
from .strategy_engine import Bar, StrategyDataError, StrategyEngine


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
    mfe_price_units: float = 0.0
    mae_price_units: float = 0.0
    breakeven_applied: bool = False


@dataclass
class BacktestState:
    balance: float
    positions: list[OpenPosition] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    pending_signals: list[dict[str, Any]] = field(default_factory=list)
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
        if self.profile["entry"]["mode"] != "MARKET":
            unsupported.append("entry.mode must be MARKET in Task 011")
        if self.profile["stop_loss"]["mode"] not in {"FIXED", "STRUCTURE"}:
            unsupported.append("stop_loss.mode supports FIXED/STRUCTURE only in Task 011")
        if self.profile["take_profit"]["mode"] not in {"FIXED", "RR"}:
            unsupported.append("take_profit.mode supports FIXED/RR only in Task 011")
        if self.profile["management"]["partial_close_enabled"]:
            unsupported.append("partial_close is reserved for later execution parity")
        if self.profile["management"]["trailing_enabled"]:
            unsupported.append("trailing is reserved for later execution parity")
        if self.profile["management"]["sl_tighten_mode"] != "OFF":
            unsupported.append("sl_tighten_mode must be OFF in Task 011")
        if self.profile["news"]["enabled"]:
            unsupported.append("news.enabled requires historical news data unavailable in Task 011")
        timezone_mode = str(self.profile["sessions"]["timezone"]).upper()
        if timezone_mode not in {"BROKER", "UTC"}:
            unsupported.append("sessions.timezone must be BROKER or UTC in Task 011")
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
        if len(state.positions) >= int(self.profile["risk"]["max_open_positions"]):
            self._skip(state, "MAX_OPEN_POSITIONS")
            return

        allowed, reason = self._entry_allowed(state, dataset, bar.time)
        if not allowed:
            self._skip(state, reason)
            return

        entry_price = bar.open + spread_price if side == "BUY" else bar.open
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
                self._skip(state, "STRUCTURE_WARMUP")
                return
            raise
        tp = self._initial_target(side, entry_price, risk_distance)
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
            signal_sequence=int(signal.get("sequence", 0)),
            signal_time=int(signal.get("bar_time", 0)),
            side=side,
            entry_time=bar.time,
            entry_price=entry_price,
            volume=volume,
            sl=sl,
            tp=tp,
            original_sl=sl,
            original_risk=risk_distance,
            profile_hash=str(signal.get("profile_hash") or strategy.profile_hash),
            dataset_fingerprint=dataset.fingerprint,
        )
        state.next_trade_id += 1
        state.positions.append(position)

        day_key = self._day_key(dataset, bar.time)
        state.trades_by_day[day_key] = state.trades_by_day.get(day_key, 0) + 1

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
        else:
            raise BacktestError(f"unsupported stop mode: {mode}")

        minimum = float(cfg["min_price_units"])
        maximum = float(cfg["max_price_units"])
        distance = max(minimum, min(maximum, distance))
        if not math.isfinite(distance) or distance <= 0:
            raise BacktestError("calculated stop distance is invalid")

        sl = entry_price - distance if side == "BUY" else entry_price + distance
        return sl, distance

    def _initial_target(
        self,
        side: str,
        entry_price: float,
        risk_distance: float,
    ) -> float:
        cfg = self.profile["take_profit"]
        if cfg["mode"] == "FIXED":
            distance = float(cfg["fixed_price_units"])
        elif cfg["mode"] == "RR":
            distance = risk_distance * float(cfg["rr_ratio"])
        else:
            raise BacktestError(f"unsupported TP mode: {cfg['mode']}")
        return entry_price + distance if side == "BUY" else entry_price - distance

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
        for position in list(state.positions):
            if position.side == "BUY":
                executable_open = bar.open
                executable_high = bar.high
                executable_low = bar.low
                favorable = max(0.0, executable_high - position.entry_price)
                adverse = max(0.0, position.entry_price - executable_low)
                gap_sl = executable_open <= position.sl
                gap_tp = executable_open >= position.tp
                touch_sl = executable_low <= position.sl
                touch_tp = executable_high >= position.tp
            else:
                executable_open = bar.open + spread_price
                executable_high = bar.high + spread_price
                executable_low = bar.low + spread_price
                favorable = max(0.0, position.entry_price - executable_low)
                adverse = max(0.0, executable_high - position.entry_price)
                gap_sl = executable_open >= position.sl
                gap_tp = executable_open <= position.tp
                touch_sl = executable_high >= position.sl
                touch_tp = executable_low <= position.tp

            position.mfe_price_units = max(position.mfe_price_units, favorable)
            position.mae_price_units = max(position.mae_price_units, adverse)

            exit_price: float | None = None
            reason: str | None = None

            if gap_sl:
                exit_price = executable_open
                reason = "SL_GAP"
            elif gap_tp:
                exit_price = executable_open
                reason = "TP_GAP"
            elif touch_sl and touch_tp:
                exit_price = position.sl
                reason = "SL_AMBIGUOUS"
            elif touch_sl:
                exit_price = position.sl
                reason = "SL"
            elif touch_tp:
                exit_price = position.tp
                reason = "TP"

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
                improves = (
                    new_sl > position.sl
                    if position.side == "BUY"
                    else new_sl < position.sl
                )
                if improves:
                    position.sl = new_sl
                    position.breakeven_applied = True

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
        price_move = (
            exit_price - position.entry_price
            if position.side == "BUY"
            else position.entry_price - exit_price
        )
        gross = (
            price_move
            / dataset.metadata.tick_size
            * dataset.metadata.tick_value
            * position.volume
        )
        commission = self.commission_per_lot * position.volume
        net = gross - commission
        state.balance += net

        duration_seconds = max(0, exit_time - position.entry_time)
        day_key = self._day_key(dataset, exit_time - 1)
        state.pnl_by_day[day_key] = state.pnl_by_day.get(day_key, 0.0) + net
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
                "entry_time": position.entry_time,
                "exit_time": exit_time,
                "entry_price": self._round(position.entry_price),
                "exit_price": self._round(exit_price),
                "volume": self._round(position.volume),
                "original_sl": self._round(position.original_sl),
                "final_sl": self._round(position.sl),
                "tp": self._round(position.tp),
                "breakeven_applied": position.breakeven_applied,
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
                    * position.volume
                ),
                "mfe_usd": self._round(
                    position.mfe_price_units
                    / dataset.metadata.tick_size
                    * dataset.metadata.tick_value
                    * position.volume
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
