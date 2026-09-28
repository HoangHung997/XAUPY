"""One explicitly armed DEMO entry, with durable consumption before dispatch.

This module never calls a broker API. The separate EA gate independently checks
the command and durably consumes its own allowance before a single OrderSend.
It is entry-path acceptance with server stops, not live position management.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time
from typing import Any
from uuid import UUID

from .config_schema import normalized_profile, validate_profile
from .execution_costs import entry_cost_plan
from .settings import _atomic_json
from .strategy_engine import HISTORY_TIMEFRAME_SECONDS, _atr


class DemoOnceError(ValueError):
    pass


class UnavailableDemoOnceController:
    """Keep ordinary monitoring available while the order allowance is unknown.

    This fallback deliberately has no filesystem or bridge access. It cannot
    repair, remove, rewrite, or reconcile the ledger that caused initialization
    to fail, and no IPC method can activate it.
    """

    def __init__(self, reason: str) -> None:
        self.reason = str(reason)[:500] or "DEMO_CONTROLLER_UNAVAILABLE"

    def status(self) -> dict[str, Any]:
        return {"schema_version": 1, "state": "UNKNOWN", "budget_consumed": True,
                "reason": self.reason, "last_blocker": self.reason, "available": False,
                "trading_enabled": False, "execution_enabled": False, "demo_one_shot_only": True,
                "automatic_retry": False, "entry_acceptance_only": True}

    def _reject(self) -> dict[str, Any]:
        return {**self.status(), "accepted": False, "code": "DEMO_CONTROLLER_UNAVAILABLE"}

    def arm(self, payload: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        return self._reject()

    def cancel(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._reject()

    def record_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._reject()

    def on_signal(self, profile: dict[str, Any]) -> None:
        return None


def _number(value: Any, name: str, *, minimum: float = 0, positive: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise DemoOnceError(f"INVALID_{name.upper()}")
    if value < minimum or (positive and value <= 0):
        raise DemoOnceError(f"INVALID_{name.upper()}")
    return float(value)


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise DemoOnceError(f"INVALID_{name.upper()}")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128 or any(c in value for c in "\r\n\0"):
        raise DemoOnceError(f"INVALID_{name.upper()}")
    return value


def profile_hash(profile: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(normalized_profile(profile), sort_keys=True,
                                    separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class DemoOnceController:
    IDENTITY = ("account_login", "account_server", "symbol", "magic", "bridge_session_id")

    def __init__(self, root_dir: str | os.PathLike[str], bridge: Any, strategy: Any) -> None:
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "demo-once-v1.json"
        self.lock_path = self.root / "demo-once-v1.lock"
        self.bridge, self.strategy = bridge, strategy
        self._data: dict[str, Any] = {"schema_version": 1, "state": "DISABLED", "budget_consumed": False}
        self._last_blocker: str | None = None
        self._io_failed = False
        with self._locked():
            self._reload()
            if self._data["state"] == "ARMED":
                self._data.update(state="SUSPENDED", reason="RESTART_REQUIRES_EXPLICIT_REARM")
                self._save()
            elif self._data["state"] == "DISPATCHED":
                self._data.update(state="UNKNOWN", reason="RESTART_REQUIRES_RECONCILIATION")
                self._save()

    @contextmanager
    def _locked(self):
        # A crash leaves a lock, deliberately failing closed instead of guessing
        # whether another process has already consumed the one-shot allowance.
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise DemoOnceError("CONTROLLER_STATE_LOCKED") from exc
        try:
            os.write(fd, str(os.getpid()).encode())
            os.fsync(fd)
            yield
        finally:
            os.close(fd)
            self.lock_path.unlink()

    def _reload(self) -> None:
        if self._io_failed:
            return
        if not self.path.exists():
            return
        try:
            if self.path.stat().st_size > 128 * 1024:
                raise ValueError("oversize state")
            value = json.loads(self.path.read_text(encoding="utf-8"))
            states = {"DISABLED", "ARMED", "SUSPENDED", "CANCELLED", "EXPIRED", "DISPATCHED", "UNKNOWN", "FILLED", "REJECTED"}
            if (not isinstance(value, dict) or type(value.get("schema_version")) is not int or value.get("schema_version") != 1
                    or value.get("state") not in states or type(value.get("budget_consumed")) is not bool):
                raise ValueError("invalid state")
            if value["state"] in {"DISPATCHED", "UNKNOWN", "FILLED", "REJECTED"} and not value["budget_consumed"]:
                raise ValueError("invalid consumption")
            if value["state"] in {"DISABLED", "ARMED", "SUSPENDED", "CANCELLED", "EXPIRED"} and value["budget_consumed"]:
                raise ValueError("contradictory consumption")
            for key in ("authorization", "command", "result", "signal_evidence"):
                if key in value and not isinstance(value[key], dict):
                    raise ValueError(f"invalid {key}")
            for key in ("armed_at_utc_ms", "armed_until_utc_ms", "armed_server_time", "observed_signal_sequence",
                        "baseline_signal_sequence", "baseline_tick_time_msc", "dispatched_at_utc_ms"):
                if key in value:
                    _integer(value[key], key)
            if "reason" in value and not isinstance(value["reason"], str):
                raise ValueError("invalid reason")
            if value["state"] in {"ARMED", "SUSPENDED", "CANCELLED", "EXPIRED", "DISPATCHED", "FILLED", "REJECTED"} or "command" in value:
                authorization = value.get("authorization")
                if not isinstance(authorization, dict):
                    raise ValueError("missing authorization")
                for key in (*self.IDENTITY, "attempt_id", "profile_hash"):
                    (_integer(authorization.get(key), key, minimum=1) if key in {"account_login", "magic"}
                     else _text(authorization.get(key), key))
                if _number(authorization.get("max_volume"), "max_volume", positive=True) > .01:
                    raise ValueError("invalid authorization cap")
                if value.get("attempt_id") != authorization["attempt_id"]:
                    raise ValueError("authorization attempt mismatch")
                for key in ("armed_at_utc_ms", "armed_until_utc_ms", "armed_server_time", "baseline_tick_time_msc"):
                    _integer(value.get(key), key, minimum=1)
                for key in ("observed_signal_sequence", "baseline_signal_sequence"):
                    _integer(value.get(key), key)
                if not 0 < value["armed_until_utc_ms"] - value["armed_at_utc_ms"] <= 86400000:
                    raise ValueError("invalid authorization deadline")
            if value["state"] in {"DISPATCHED", "FILLED", "REJECTED"} or "command" in value:
                command = value.get("command")
                if not isinstance(command, dict):
                    raise ValueError("missing dispatched command")
                for key in (*self.IDENTITY, "attempt_id", "profile_hash"):
                    if command.get(key) != value["authorization"][key]:
                        raise ValueError("command authorization mismatch")
                if command.get("kind") != "DEMO_ONE_SHOT_MARKET" or command.get("side") not in {"BUY", "SELL"}:
                    raise ValueError("invalid command kind or side")
                for key in ("volume", "reference_price", "sl", "tp", "max_loss_money"):
                    _number(command.get(key), key, positive=True)
                _number(command.get("max_spread_price_units"), "max_spread_price_units")
                for key in ("max_deviation_points", "issued_server_time", "expires_server_time", "signal_sequence", "signal_bar_time"):
                    _integer(command.get(key), key)
                if command["volume"] > min(.01, value["authorization"]["max_volume"]):
                    raise ValueError("invalid command volume")
                if not 0 < command["expires_server_time"] - command["issued_server_time"] <= 5:
                    raise ValueError("invalid command expiry")
                _number(value.get("tick_size"), "tick_size", positive=True)
                _integer(value.get("dispatched_at_utc_ms"), "dispatched_at_utc_ms", minimum=1)
            if value["state"] in {"FILLED", "REJECTED"} or "result" in value:
                result, command = value.get("result"), value.get("command")
                if not isinstance(result, dict) or not isinstance(command, dict):
                    raise ValueError("missing result or command")
                if any(result.get(key) != command[key] for key in (*self.IDENTITY, "attempt_id")):
                    raise ValueError("result identity mismatch")
                if type(result.get("order_send_called")) is not bool:
                    raise ValueError("invalid result send flag")
                for key in ("retcode", "retcode_external", "order_ticket", "deal_ticket"):
                    _integer(result.get(key), key)
                for key in ("filled_volume", "fill_price", "sl", "tp"):
                    _number(result.get(key), key)
                if result["filled_volume"] > command["volume"] + 1e-12:
                    raise ValueError("invalid result volume")
                if value["state"] == "FILLED" and (not result["order_send_called"] or result["retcode"] not in {10008, 10009, 10010}
                                                   or result["deal_ticket"] <= 0 or result["filled_volume"] <= 0 or result["fill_price"] <= 0):
                    raise ValueError("missing filled evidence")
                if value["state"] == "FILLED":
                    tolerance = value["tick_size"] / 2 + 1e-10
                    protective = (0 < result["sl"] < result["fill_price"] < result["tp"] if command["side"] == "BUY"
                                  else 0 < result["tp"] < result["fill_price"] < result["sl"])
                    if not protective or any(abs(result[key] - command[key]) > tolerance for key in ("sl", "tp")):
                        raise ValueError("invalid filled protection")
            self._data = value
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            self._data = {"schema_version": 1, "state": "UNKNOWN", "budget_consumed": True,
                          "reason": "STATE_INVALID_RECONCILIATION_REQUIRED"}
            self._io_failed = True

    def _save(self) -> None:
        try:
            _atomic_json(self.path, self._data)
        except OSError:
            # The durable write may have completed before an I/O error. Never
            # release an order or retry on the strength of in-memory state.
            self._data.update(state="UNKNOWN", budget_consumed=True, reason="STATE_WRITE_FAILED")
            self._io_failed = True
            raise

    def status(self) -> dict[str, Any]:
        self._reload()
        now_ms = time.time() * 1000
        armed_expired = self._data["state"] == "ARMED" and now_ms >= self._data["armed_until_utc_ms"]
        result_overdue = self._data["state"] == "DISPATCHED" and now_ms >= self._data.get("dispatched_at_utc_ms", 0) + 30000
        if armed_expired or result_overdue:
            try:
                with self._locked():
                    self._reload()
                    if self._data["state"] == "ARMED" and time.time() * 1000 >= self._data["armed_until_utc_ms"]:
                        self._data.update(state="EXPIRED", reason="ARM_DURATION_EXPIRED")
                        self._save()
                    elif self._data["state"] == "DISPATCHED" and time.time() * 1000 >= self._data.get("dispatched_at_utc_ms", 0) + 30000:
                        self._data.update(state="UNKNOWN", reason="BROKER_RESULT_TIMEOUT_NO_RETRY")
                        self._save()
            except (DemoOnceError, OSError):
                self._last_blocker = "STATE_IO_ERROR"
        return self._public_status()

    def _public_status(self) -> dict[str, Any]:
        result = {k: deepcopy(v) for k, v in self._data.items() if k not in {"command", "signal_evidence"}}
        command, broker_result = self._data.get("command", {}), self._data.get("result", {})
        for key in ("side", "volume", "sl", "tp"):
            if key in command:
                result[key] = command[key]
        for key in ("order_ticket", "deal_ticket", "filled_volume", "fill_price"):
            if key in broker_result:
                result[key] = broker_result[key]
        if self._data["state"] == "FILLED":
            result["authorized_volume"] = command.get("volume")
            result["volume"] = broker_result.get("filled_volume")
        result.update(last_blocker=self._last_blocker, trading_enabled=False,
                      execution_enabled=False, demo_one_shot_only=True, automatic_retry=False,
                      entry_acceptance_only=True)
        return result

    def _response(self, accepted: bool, code: str) -> dict[str, Any]:
        return {**self._public_status(), "accepted": accepted, "code": code}

    def _profile_guard(self, profile: dict[str, Any]) -> str:
        errors = validate_profile(profile)
        if errors:
            raise DemoOnceError("INVALID_PROFILE")
        if profile["entry"]["mode"] != "MARKET":
            raise DemoOnceError("UNSUPPORTED_ENTRY_MODE")
        if profile["take_profit"]["mode"] not in {"FIXED", "RR"}:
            raise DemoOnceError("UNSUPPORTED_TP_MODE")
        if profile["news"]["enabled"]:
            raise DemoOnceError("NEWS_GUARD_UNAVAILABLE")
        if profile["sessions"]["timezone"].upper() not in {"BROKER", "UTC"}:
            raise DemoOnceError("UNSUPPORTED_SESSION_TIMEZONE")
        return profile_hash(profile)

    def _snapshot(self) -> dict[str, Any]:
        snapshot = self.bridge.latest_fresh_snapshot()
        if not isinstance(snapshot, dict):
            raise DemoOnceError("STALE_MARKET_DATA")
        if snapshot.get("terminal_connected") is not True or snapshot.get("account_trade_mode") != "DEMO":
            raise DemoOnceError("DEMO_CONNECTED_ACCOUNT_REQUIRED")
        if snapshot.get("demo_once_capable") is not True:
            raise DemoOnceError("EA_CAPABILITY_REQUIRED")
        if snapshot.get("demo_once_consumed") is not False:
            raise DemoOnceError("EA_ONE_SHOT_UNAVAILABLE")
        for key in self.IDENTITY:
            (_integer(snapshot.get(key), key, minimum=1) if key in {"account_login", "magic"}
             else _text(snapshot.get(key), key))
        server_time = _integer(snapshot.get("server_time"), "server_time", minimum=1)
        tick_time = _integer(snapshot.get("tick_time_msc"), "tick_time_msc", minimum=1)
        if not -2000 <= server_time * 1000 - tick_time <= 5000:
            raise DemoOnceError("STALE_QUOTE")
        bid = _number(snapshot.get("bid"), "bid", positive=True)
        ask = _number(snapshot.get("ask"), "ask", positive=True)
        if ask < bid:
            raise DemoOnceError("REVERSED_QUOTE")
        guardian = snapshot.get("guardian", {})
        if not isinstance(guardian, dict):
            raise DemoOnceError("EA_GUARDIAN_REQUIRED")
        for flag in ("terminal_trade_allowed", "mql_trade_allowed"):
            if guardian.get(flag) is not True:
                raise DemoOnceError(flag.upper())
        guard = snapshot.get("demo_once_guard")
        if not isinstance(guard, dict) or guard.get("history_complete") is not True:
            raise DemoOnceError("BROKER_RISK_HISTORY_REQUIRED")
        for flag in ("account_trade_allowed", "account_expert_allowed"):
            if guard.get(flag) is not True:
                raise DemoOnceError(flag.upper())
        return snapshot

    def arm(self, payload: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._locked():
                self._reload()
                if self._data["budget_consumed"]:
                    return self._response(False, "ONE_SHOT_ALREADY_CONSUMED")
                if not isinstance(payload, dict) or payload.get("confirmed") is not True:
                    raise DemoOnceError("CONFIRMATION_REQUIRED")
                attempt = _text(payload.get("attempt_id"), "attempt_id")
                try:
                    UUID(attempt)
                except ValueError as exc:
                    raise DemoOnceError("INVALID_ATTEMPT_ID") from exc
                active_hash = self._profile_guard(profile)
                if payload.get("profile_hash") != active_hash or self.strategy.profile_hash != active_hash:
                    raise DemoOnceError("PROFILE_HASH_MISMATCH")
                snapshot = self._snapshot()
                for key in ("account_login", "magic"):
                    _integer(payload.get(key), key, minimum=1)
                for key in ("account_server", "symbol"):
                    _text(payload.get(key), key)
                if any(payload.get(key) != snapshot[key] for key in self.IDENTITY if key != "bridge_session_id"):
                    raise DemoOnceError("ACCOUNT_OR_SYMBOL_MISMATCH")
                if profile["strategy"]["symbol"] != snapshot["symbol"] or profile["execution"]["magic"] != snapshot["magic"]:
                    raise DemoOnceError("PROFILE_IDENTITY_MISMATCH")
                volume = _number(payload.get("max_volume"), "max_volume", positive=True)
                if volume > .01:
                    raise DemoOnceError("VOLUME_LIMIT_001")
                duration = _integer(payload.get("duration_seconds"), "duration_seconds", minimum=1)
                if duration > 86400:
                    raise DemoOnceError("DURATION_LIMIT")
                authorization = {key: snapshot[key] for key in self.IDENTITY}
                authorization.update(attempt_id=attempt, profile_hash=active_hash, max_volume=volume)
                if self._data["state"] == "ARMED" and time.time() * 1000 >= self._data["armed_until_utc_ms"]:
                    self._data.update(state="EXPIRED", reason="ARM_DURATION_EXPIRED")
                    self._save()
                if self._data["state"] == "ARMED":
                    if authorization == self._data.get("authorization"):
                        return self._response(True, "ALREADY_ARMED")
                    raise DemoOnceError("ANOTHER_AUTHORIZATION_ACTIVE")
                strategy_status = self.strategy.status_payload(market_connected=True)
                if not strategy_status.get("available") or not strategy_status.get("ready"):
                    raise DemoOnceError("STRATEGY_NOT_READY")
                _integer(strategy_status.get("signal_sequence"), "signal_sequence")
                self._risk_guard(snapshot, profile, check_session=False)
                self._volume(snapshot, profile, volume)
                now = time.time()
                self._data = {"schema_version": 1, "state": "ARMED", "budget_consumed": False,
                              "authorization": authorization, "attempt_id": attempt,
                              "armed_at_utc_ms": int(now * 1000), "armed_until_utc_ms": int((now + duration) * 1000),
                              "armed_until_utc": datetime.fromtimestamp(now + duration, timezone.utc).isoformat(),
                              "armed_server_time": snapshot["server_time"],
                              "baseline_signal_sequence": strategy_status["signal_sequence"],
                              "observed_signal_sequence": strategy_status["signal_sequence"],
                              "baseline_tick_time_msc": snapshot["tick_time_msc"], "reason": "WAIT_NEW_STRATEGY_SIGNAL"}
                self._last_blocker = None
                self._save()
                return self._response(True, "ARMED")
        except (DemoOnceError, OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
            return self._response(False, str(exc) if isinstance(exc, DemoOnceError) else "FAIL_CLOSED_DATA_OR_STATE_ERROR")

    def cancel(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._locked():
                self._reload()
                if (not isinstance(payload, dict) or not isinstance(self._data.get("attempt_id"), str)
                        or payload.get("attempt_id") != self._data["attempt_id"]):
                    raise DemoOnceError("ATTEMPT_MISMATCH")
                if self._data["budget_consumed"]:
                    raise DemoOnceError("ALREADY_DISPATCHED_CANNOT_CANCEL")
                self._data.update(state="CANCELLED", reason="USER_CANCELLED")
                self._save()
                return self._response(True, "CANCELLED")
        except (DemoOnceError, OSError) as exc:
            return self._response(False, str(exc) if isinstance(exc, DemoOnceError) else "STATE_IO_ERROR")

    def _risk_guard(self, snapshot: dict[str, Any], profile: dict[str, Any], *, check_session: bool = True) -> None:
        guard, risk = snapshot["demo_once_guard"], profile["risk"]
        now = snapshot["server_time"]
        day_start = _integer(guard.get("broker_day_start"), "broker_day_start", minimum=1)
        if day_start != now // 86400 * 86400:
            raise DemoOnceError("BROKER_DAY_HISTORY_MISMATCH")
        if any(_integer(guard.get(key), key) != 0 for key in ("symbol_positions", "symbol_orders")):
            raise DemoOnceError("SYMBOL_ALREADY_EXPOSED")
        if _integer(guard.get("trades_today"), "trades_today") >= risk["max_trades_per_day"]:
            raise DemoOnceError("MAX_TRADES_PER_DAY")
        if _integer(guard.get("consecutive_losses"), "consecutive_losses") >= risk["max_consecutive_losses"]:
            raise DemoOnceError("MAX_CONSECUTIVE_LOSSES")
        day_balance = _number(guard.get("day_start_balance"), "day_start_balance", positive=True)
        pnl = _number(guard.get("daily_realized"), "daily_realized", minimum=-math.inf)
        if pnl <= -day_balance * risk["max_daily_loss_pct"] / 100:
            raise DemoOnceError("DAILY_LOSS_LIMIT")
        if risk["stop_after_daily_target"] and pnl >= day_balance * risk["daily_target_pct"] / 100:
            raise DemoOnceError("DAILY_TARGET_REACHED")
        last_exit = _integer(guard.get("last_exit_time"), "last_exit_time")
        if last_exit > now or (last_exit and now - last_exit < risk["cooldown_minutes"] * 60):
            raise DemoOnceError("COOLDOWN")
        if snapshot["ask"] - snapshot["bid"] > profile["costs"]["max_spread_price_units"] + 1e-12:
            raise DemoOnceError("SPREAD_LIMIT")
        if check_session:
            # MT5 calendar timestamps are retained in the bridge. UTC needs an
            # explicit broker offset; do not guess the account's timezone.
            seconds = now
            if profile["sessions"]["timezone"].upper() == "UTC":
                offset = snapshot.get("server_utc_offset_seconds")
                if type(offset) is not int or abs(offset) > 18 * 3600:
                    raise DemoOnceError("BROKER_UTC_OFFSET_REQUIRED")
                seconds -= offset
            dt = datetime.fromtimestamp(seconds, timezone.utc)
            sessions = profile["sessions"]
            if not sessions[("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[dt.weekday()]]:
                raise DemoOnceError("SESSION_DAY_BLOCKED")
            minute = dt.hour * 60 + dt.minute
            windows = []
            for i in (1, 2):
                if sessions[f"session{i}_enabled"]:
                    def minutes(value: str) -> int:
                        hour, minute = map(int, value.split(":"))
                        return hour * 60 + minute
                    windows.append((minutes(sessions[f"session{i}_start"]), minutes(sessions[f"session{i}_end"])))
            if windows and not any(a == b or (a <= minute < b if a < b else minute >= a or minute < b) for a, b in windows):
                raise DemoOnceError("SESSION_TIME_BLOCKED")

    def _volume(self, snapshot: dict[str, Any], profile: dict[str, Any], cap: float) -> float:
        minimum = _number(snapshot.get("volume_min"), "volume_min", positive=True)
        step = _number(snapshot.get("volume_step"), "volume_step", positive=True)
        maximum = _number(snapshot.get("volume_max"), "volume_max", positive=True)
        cap = min(cap, .01, maximum, profile["risk"]["max_lot"],
                  _number(snapshot["guardian"].get("max_volume"), "ea_max_volume", positive=True))
        if profile["risk"]["sizing_mode"] == "FIXED_LOT":
            cap = min(cap, profile["risk"]["fixed_lot"])
        volume = math.floor((cap + 1e-12) / step) * step
        if volume < minimum - 1e-12 or volume <= 0 or volume > .01 + 1e-12:
            raise DemoOnceError("BROKER_VOLUME_NOT_WITHIN_001")
        return round(volume, 8)

    def _command(self, profile: dict[str, Any], snapshot: dict[str, Any], signal: dict[str, Any]) -> dict[str, Any]:
        auth = self._data["authorization"]
        side = signal.get("side")
        if side not in {"BUY", "SELL"} or not profile["strategy"][f"allow_{side.lower()}"]:
            raise DemoOnceError("SIGNAL_SIDE_DISABLED")
        entry = snapshot["ask" if side == "BUY" else "bid"]
        close_side = snapshot["bid" if side == "BUY" else "ask"]
        spread = snapshot["ask"] - snapshot["bid"]
        tick_size = _number(snapshot.get("tick_size"), "tick_size", positive=True)
        point = _number(snapshot.get("point"), "point", positive=True)
        tick_value = _number(snapshot.get("tick_value_loss", snapshot.get("tick_value")), "tick_value_loss", positive=True)
        minimum_stop = _integer(snapshot.get("stops_level"), "stops_level") * point
        cfg = profile["stop_loss"]
        mode = cfg["mode"]
        if mode == "FIXED":
            distance = cfg["fixed_price_units"]
        else:
            timeframe = cfg["structure_timeframe" if mode == "STRUCTURE" else "atr_timeframe"]
            bars = [b for b in self.strategy.history[timeframe]
                    if b.time + HISTORY_TIMEFRAME_SECONDS[timeframe] <= snapshot["server_time"]]
            span = HISTORY_TIMEFRAME_SECONDS[timeframe]
            if not bars or bars[-1].time != (snapshot["server_time"] // span - 1) * span:
                raise DemoOnceError("STOP_HISTORY_STALE")
            if mode == "STRUCTURE":
                lookback = cfg["structure_lookback"]
                if len(bars) < lookback:
                    raise DemoOnceError("STOP_HISTORY_WARMUP")
                raw = (min(b.low for b in bars[-lookback:]) - cfg["structure_buffer_price_units"] if side == "BUY"
                       else max(b.high for b in bars[-lookback:]) + cfg["structure_buffer_price_units"] + spread)
                distance = entry - raw if side == "BUY" else raw - entry
            elif mode == "ATR":
                atr = _atr(bars, cfg["atr_period"])
                if atr is None:
                    raise DemoOnceError("STOP_HISTORY_WARMUP")
                distance = atr * cfg["atr_multiplier"]
            else:
                raise DemoOnceError("UNSUPPORTED_SL_MODE")
        distance = max(cfg["min_price_units"], min(cfg["max_price_units"], distance))
        raw_sl = entry - distance if side == "BUY" else entry + distance
        sl = (math.floor(raw_sl / tick_size + 1e-10) if side == "BUY" else math.ceil(raw_sl / tick_size - 1e-10)) * tick_size
        risk_distance = abs(entry - sl)
        tp_cfg = profile["take_profit"]
        reward = tp_cfg["fixed_price_units"] if tp_cfg["mode"] == "FIXED" else risk_distance * tp_cfg["rr_ratio"]
        raw_tp = entry + reward if side == "BUY" else entry - reward
        # Conservative target rounding preserves canonical initial target rules.
        tp = (math.floor(raw_tp / tick_size + 1e-10) if side == "BUY" else math.ceil(raw_tp / tick_size - 1e-10)) * tick_size
        stop_distance = close_side - sl if side == "BUY" else sl - close_side
        target_distance = tp - close_side if side == "BUY" else close_side - tp
        if (not all(math.isfinite(v) and v > 0 for v in (sl, tp, risk_distance, stop_distance, target_distance))
                or min(stop_distance, target_distance) + 1e-12 < minimum_stop
                or risk_distance > cfg["max_price_units"] + 1e-10):
            raise DemoOnceError("INVALID_SERVER_STOPS")
        volume = self._volume(snapshot, profile, auth["max_volume"])
        balance = _number(snapshot.get("balance"), "balance", positive=True)
        max_loss = balance * profile["risk"]["risk_percent"] / 100
        guard = snapshot["demo_once_guard"]
        remaining_day_loss = guard["day_start_balance"] * profile["risk"]["max_daily_loss_pct"] / 100 + min(guard["daily_realized"], 0)
        max_loss = min(max_loss, remaining_day_loss)
        ea_daily_limit = _number(snapshot["guardian"].get("daily_loss_limit"), "ea_daily_loss_limit", positive=True)
        max_loss = min(max_loss, ea_daily_limit + min(guard["daily_realized"], 0))
        costs = entry_cost_plan(profile, risk_distance=risk_distance,
                                target_distance=abs(tp - entry), spread_price=spread,
                                point=point, tick_size=tick_size, tick_value=tick_value)
        planned_loss = costs.loss_per_lot * volume
        if planned_loss > max_loss + 1e-10:
            raise DemoOnceError("RISK_BUDGET_EXCEEDED")
        if costs.blocker:
            raise DemoOnceError(costs.blocker)
        return {"kind": "DEMO_ONE_SHOT_MARKET", **auth, "side": side, "volume": volume,
                "reference_price": entry, "sl": round(sl, 10), "tp": round(tp, 10),
                "max_deviation_points": profile["costs"]["max_slippage_points"],
                "max_spread_price_units": profile["costs"]["max_spread_price_units"], "max_loss_money": max_loss,
                "issued_server_time": snapshot["server_time"], "expires_server_time": snapshot["server_time"] + 5,
                "signal_sequence": signal["sequence"], "signal_bar_time": signal["bar_time"]}

    def on_signal(self, profile: dict[str, Any]) -> dict[str, Any] | None:
        try:
            with self._locked():
                self._reload()
                if self._data["state"] != "ARMED" or self._data["budget_consumed"]:
                    return None
                if time.time() * 1000 >= self._data["armed_until_utc_ms"]:
                    self._data.update(state="EXPIRED", reason="ARM_DURATION_EXPIRED")
                    self._save()
                    return None
                auth = self._data["authorization"]
                if self._profile_guard(profile) != auth["profile_hash"] or self.strategy.profile_hash != auth["profile_hash"]:
                    self._data.update(state="SUSPENDED", reason="PROFILE_CHANGED")
                    self._save()
                    return None
                status = self.strategy.status_payload(market_connected=True)
                signal = status.get("last_signal")
                sequence = _integer(signal.get("sequence"), "signal_sequence", minimum=1) if isinstance(signal, dict) else 0
                new_signal = sequence > self._data["observed_signal_sequence"]
                if new_signal:
                    # Consume this observation before every gate, including
                    # quote/permission failures. Clearing a guard cannot revive
                    # an already rejected signal later in its freshness window.
                    self._data["observed_signal_sequence"] = sequence
                    self._save()
                snapshot = self._snapshot()
                if any(snapshot[key] != auth[key] for key in self.IDENTITY):
                    self._data.update(state="SUSPENDED", reason="BRIDGE_IDENTITY_CHANGED")
                    self._save()
                    return None
                if not status.get("ready") or not status.get("available") or not new_signal:
                    return None
                bar_time = _integer(signal.get("bar_time"), "signal_bar_time", minimum=1)
                span = HISTORY_TIMEFRAME_SECONDS[profile["timeframes"]["trigger"]]
                event_time = signal.get("tick_time_msc")
                if event_time is None:
                    event_time = (bar_time + span) * 1000
                event_time = _integer(event_time, "signal_time", minimum=1)
                if (signal.get("profile_hash") != auth["profile_hash"] or status.get("state") != f"TRIGGERED_{signal.get('side')}"
                        or sequence != status.get("signal_sequence")
                        or event_time <= self._data["armed_server_time"] * 1000
                        or event_time <= self._data["baseline_tick_time_msc"]
                        or event_time > (snapshot["server_time"] + 2) * 1000
                        or snapshot["server_time"] * 1000 - event_time > 5000
                        or snapshot["tick_time_msc"] <= self._data["baseline_tick_time_msc"]):
                    raise DemoOnceError("SIGNAL_NOT_FRESH_AFTER_ARM")
                self._risk_guard(snapshot, profile)
                command = self._command(profile, snapshot, signal)
                command.pop("max_volume", None)
                self._data.update(state="DISPATCHED", budget_consumed=True, reason="AWAITING_BROKER_EVIDENCE",
                                  dispatched_at_utc_ms=int(time.time() * 1000), tick_size=snapshot["tick_size"],
                                  command=command, signal_evidence=deepcopy(signal))
                self._save()
                self._last_blocker = None
                return deepcopy(command)
        except (DemoOnceError, OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
            self._last_blocker = str(exc) if isinstance(exc, DemoOnceError) else "FAIL_CLOSED_DATA_OR_STATE_ERROR"
            return None

    def record_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._locked():
                self._reload()
                command = self._data.get("command")
                if not self._data["budget_consumed"] or not isinstance(command, dict):
                    raise DemoOnceError("NO_DISPATCHED_COMMAND")
                if not isinstance(payload, dict) or any(payload.get(key) != command[key] for key in (*self.IDENTITY, "attempt_id")):
                    raise DemoOnceError("RESULT_IDENTITY_MISMATCH")
                for key in ("account_login", "magic", "retcode", "retcode_external", "order_ticket", "deal_ticket"):
                    _integer(payload.get(key), key)
                if type(payload.get("order_send_called")) is not bool:
                    raise DemoOnceError("INVALID_ORDER_SEND_CALLED")
                for key in ("filled_volume", "fill_price", "sl", "tp"):
                    _number(payload.get(key), key)
                if payload["filled_volume"] > command["volume"] + 1e-12:
                    raise DemoOnceError("RESULT_VOLUME_EXCEEDED")
                if self._data["state"] == "FILLED":
                    return self._response(True, "ALREADY_FILLED")
                tick_tolerance = _number(self._data.get("tick_size"), "recorded_tick_size", positive=True) / 2
                filled = (payload.get("status") == "FILLED" and payload["order_send_called"]
                          and payload["retcode"] in {10008, 10009, 10010} and payload["deal_ticket"] > 0
                          and payload["filled_volume"] > 0 and payload["fill_price"] > 0
                          and abs(payload["sl"] - command["sl"]) <= tick_tolerance + 1e-10
                          and abs(payload["tp"] - command["tp"]) <= tick_tolerance + 1e-10
                          and (0 < payload["sl"] < payload["fill_price"] < payload["tp"] if command["side"] == "BUY"
                               else 0 < payload["tp"] < payload["fill_price"] < payload["sl"]))
                result = {key: payload[key] for key in (*self.IDENTITY, "attempt_id", "order_send_called", "retcode",
                          "retcode_external", "order_ticket", "deal_ticket", "filled_volume", "fill_price", "sl", "tp")}
                result["reason"] = str(payload.get("reason", ""))[:500]
                # The pre-send durable claim says UNKNOWN with called=false:
                # a crash may have followed OrderSend but preceded result save.
                # Only an explicit final rejection can establish that no send
                # occurred; a false flag by itself is never such evidence.
                rejected = payload.get("status") == "REJECTED" and not payload["order_send_called"]
                self._data.update(state="FILLED" if filled else "REJECTED" if rejected else "UNKNOWN",
                                  reason="BROKER_DEAL_CONFIRMED" if filled else "EA_REJECTED_NO_RETRY" if rejected else "RECONCILIATION_REQUIRED",
                                  result=result)
                self._save()
                return self._response(True, self._data["state"])
        except (DemoOnceError, OSError) as exc:
            return self._response(False, str(exc) if isinstance(exc, DemoOnceError) else "STATE_IO_ERROR")
