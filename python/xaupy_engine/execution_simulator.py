from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import json
import math
from typing import Any
from uuid import UUID

from .bridge_state import BridgeRegistry
from .config_schema import get_path


class ManualActionSimulator:
    """Deterministic Task 009 dry-run executor.

    It validates the exact same class of broker-like controls the Desktop exposes,
    but it never mutates MT5 and never returns execution_enabled=true.
    """

    SUPPORTED_ACTIONS = {
        "MARKET_BUY",
        "MARKET_SELL",
        "CLOSE_POSITION",
        "PARTIAL_CLOSE",
        "MOVE_SL_BE",
        "START_TRAILING",
        "MODIFY_PENDING",
        "CANCEL_PENDING",
        "CLOSE_ALL",
        "CLOSE_PROFIT",
        "CLOSE_LOSS",
        "CANCEL_ALL_PENDING",
    }
    MAX_CACHED_INTENTS = 256

    def __init__(self, bridge: BridgeRegistry) -> None:
        self.bridge = bridge
        self._cache: OrderedDict[str, tuple[str, dict[str, Any]]] = OrderedDict()

    def simulate(
        self,
        payload: dict[str, Any],
        active_profile: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return self._result(
                None,
                None,
                False,
                "INVALID_PAYLOAD",
                "manual action payload must be an object",
            )

        intent_id = payload.get("intent_id")
        action = payload.get("action")
        if not isinstance(intent_id, str) or not self._is_uuid(intent_id):
            return self._result(
                None,
                action if isinstance(action, str) else None,
                False,
                "INVALID_INTENT_ID",
                "intent_id must be a UUID",
            )

        normalized_action = action.upper().strip() if isinstance(action, str) else ""
        fingerprint = self._fingerprint(payload)

        cached = self._cache.get(intent_id)
        if cached is not None:
            cached_fingerprint, cached_result = cached
            if cached_fingerprint != fingerprint:
                return self._result(
                    intent_id,
                    normalized_action or None,
                    False,
                    "INTENT_ID_CONFLICT",
                    "intent_id was already used for different action content",
                )
            return deepcopy(cached_result)

        if normalized_action not in self.SUPPORTED_ACTIONS:
            return self._remember(
                intent_id,
                fingerprint,
                self._result(
                    intent_id,
                    normalized_action or None,
                    False,
                    "UNSUPPORTED_ACTION",
                    f"Unsupported manual action: {normalized_action or '?'}",
                ),
            )

        guard_error = self._common_guard(payload, active_profile)
        if guard_error is not None:
            code, message = guard_error
            return self._remember(
                intent_id,
                fingerprint,
                self._result(intent_id, normalized_action, False, code, message),
            )

        snapshot = self.bridge.latest_fresh_snapshot()
        assert snapshot is not None

        handlers = {
            "MARKET_BUY": self._simulate_market,
            "MARKET_SELL": self._simulate_market,
            "CLOSE_POSITION": self._simulate_close_position,
            "PARTIAL_CLOSE": self._simulate_partial_close,
            "MOVE_SL_BE": self._simulate_move_sl_be,
            "START_TRAILING": self._simulate_start_trailing,
            "MODIFY_PENDING": self._simulate_modify_pending,
            "CANCEL_PENDING": self._simulate_cancel_pending,
            "CLOSE_ALL": self._simulate_bulk_close,
            "CLOSE_PROFIT": self._simulate_bulk_close,
            "CLOSE_LOSS": self._simulate_bulk_close,
            "CANCEL_ALL_PENDING": self._simulate_cancel_all_pending,
        }

        accepted, code, message, preview = handlers[normalized_action](
            normalized_action,
            payload,
            snapshot,
            active_profile,
        )
        return self._remember(
            intent_id,
            fingerprint,
            self._result(
                intent_id,
                normalized_action,
                accepted,
                code,
                message,
                preview,
            ),
        )

    def _common_guard(
        self,
        payload: dict[str, Any],
        active_profile: dict[str, Any],
    ) -> tuple[str, str] | None:
        if payload.get("confirmed") is not True:
            return "CONFIRMATION_REQUIRED", "explicit confirmation is required"

        try:
            if get_path(active_profile, "execution.demo_only") is not True:
                return "SAFETY_PROFILE_INVALID", "execution.demo_only must remain true"
            if get_path(active_profile, "execution.allow_real_account") is not False:
                return "SAFETY_PROFILE_INVALID", "execution.allow_real_account must remain false"
            if int(get_path(active_profile, "execution.max_retry_count")) != 0:
                return "SAFETY_PROFILE_INVALID", "execution.max_retry_count must remain zero"
            if get_path(active_profile, "safety.block_on_stale_market_data") is not True:
                return "SAFETY_PROFILE_INVALID", "stale-market blocking must remain enabled"
        except (KeyError, TypeError, ValueError):
            return "SAFETY_PROFILE_INVALID", "active profile safety fields are unavailable"

        snapshot = self.bridge.latest_fresh_snapshot()
        if snapshot is None:
            return "STALE_MARKET_DATA", "fresh MT5 Bridge snapshot is required"

        if snapshot.get("terminal_connected") is not True:
            return "TERMINAL_DISCONNECTED", "MT5 terminal must be connected"

        if str(snapshot.get("account_trade_mode", "")).upper() != "DEMO":
            return "DEMO_ONLY", "Task 009 manual simulation requires a DEMO account"

        try:
            configured_symbol = str(get_path(active_profile, "strategy.symbol"))
        except KeyError:
            return "SAFETY_PROFILE_INVALID", "active profile symbol is unavailable"

        if str(snapshot.get("symbol", "")) != configured_symbol:
            return "SYMBOL_MISMATCH", "Bridge symbol does not match active profile"

        return None

    def _simulate_market(
        self,
        action: str,
        payload: dict[str, Any],
        snapshot: dict[str, Any],
        profile: dict[str, Any],
    ) -> tuple[bool, str, str, dict[str, Any] | None]:
        volume_error = self._validate_volume(payload.get("volume"), snapshot, profile)
        if volume_error is not None:
            return False, volume_error[0], volume_error[1], None

        volume = float(payload["volume"])
        positions = self._objects(snapshot.get("positions"))
        max_positions = int(get_path(profile, "risk.max_open_positions"))
        if len(positions) >= max_positions:
            return False, "MAX_OPEN_POSITIONS", "active max_open_positions would be exceeded", None

        guardian = snapshot.get("guardian")
        if isinstance(guardian, dict):
            daily_realized = self._number(guardian.get("daily_realized"))
            daily_limit = self._positive(guardian.get("daily_loss_limit"))
            if daily_limit is not None and daily_realized <= -daily_limit:
                return False, "DAILY_LOSS_LIMIT", "daily loss guard is active", None

        side = "BUY" if action == "MARKET_BUY" else "SELL"
        entry = self._positive(snapshot.get("ask" if side == "BUY" else "bid"))
        point = self._positive(snapshot.get("point"))
        if entry is None or point is None:
            return False, "MARKET_PRICE_UNAVAILABLE", "current market price/point is unavailable", None

        sl_points = self._positive(payload.get("sl_points"))
        tp_points = self._positive(payload.get("tp_points"))
        if get_path(profile, "safety.require_server_sl") is True and sl_points is None:
            return False, "SERVER_SL_REQUIRED", "SL distance is required by hard safety", None

        stops_level = max(0, int(self._number(snapshot.get("stops_level"))))
        if sl_points is not None and sl_points < stops_level:
            return False, "SL_TOO_CLOSE", "SL distance violates broker stops level", None
        if tp_points is not None and tp_points < stops_level:
            return False, "TP_TOO_CLOSE", "TP distance violates broker stops level", None

        sl = None
        tp = None
        if sl_points is not None:
            sl = entry - sl_points * point if side == "BUY" else entry + sl_points * point
        if tp_points is not None:
            tp = entry + tp_points * point if side == "BUY" else entry - tp_points * point

        preview = {
            "side": side,
            "symbol": snapshot.get("symbol"),
            "volume": volume,
            "simulated_fill_price": entry,
            "server_sl": sl,
            "take_profit": tp,
            "sl_points": sl_points,
            "tp_points": tp_points,
            "broker_request_sent": False,
        }
        return True, "SIMULATED_ACCEPTED", "market action passed guards; broker was not mutated", preview

    def _simulate_close_position(
        self,
        action: str,
        payload: dict[str, Any],
        snapshot: dict[str, Any],
        profile: dict[str, Any],
    ) -> tuple[bool, str, str, dict[str, Any] | None]:
        position = self._find_ticket(snapshot.get("positions"), payload.get("ticket"))
        if position is None:
            return False, "POSITION_NOT_FOUND", "target position is not owned/present in latest snapshot", None

        side = str(position.get("side", "")).upper()
        close_price = self._positive(snapshot.get("bid" if side == "BUY" else "ask"))
        if close_price is None:
            return False, "MARKET_PRICE_UNAVAILABLE", "close-side market price is unavailable", None

        return True, "SIMULATED_ACCEPTED", "close preview passed guards; broker was not mutated", {
            "ticket": position.get("ticket"),
            "side": side,
            "volume": position.get("volume"),
            "simulated_close_price": close_price,
            "broker_request_sent": False,
        }

    def _simulate_partial_close(
        self,
        action: str,
        payload: dict[str, Any],
        snapshot: dict[str, Any],
        profile: dict[str, Any],
    ) -> tuple[bool, str, str, dict[str, Any] | None]:
        position = self._find_ticket(snapshot.get("positions"), payload.get("ticket"))
        if position is None:
            return False, "POSITION_NOT_FOUND", "target position is not owned/present in latest snapshot", None

        volume = self._positive(position.get("volume"))
        if volume is None:
            return False, "POSITION_VOLUME_INVALID", "position volume is unavailable", None

        percent = self._positive(payload.get("percent"))
        if percent is None:
            percent = float(get_path(profile, "management.partial_close_percent"))
        if not (0 < percent < 100):
            return False, "PARTIAL_PERCENT_INVALID", "partial close percent must be between 0 and 100", None

        step = self._positive(snapshot.get("volume_step")) or 0.01
        minimum = self._positive(snapshot.get("volume_min")) or step
        close_volume = math.floor((volume * percent / 100.0) / step + 1e-9) * step
        close_volume = round(close_volume, 8)
        remaining = round(volume - close_volume, 8)

        if close_volume < minimum:
            return False, "PARTIAL_VOLUME_TOO_SMALL", "partial close volume is below broker minimum", None
        if remaining > 1e-9 and remaining < minimum:
            return False, "PARTIAL_REMAINDER_TOO_SMALL", "remaining position would be below broker minimum", None

        return True, "SIMULATED_ACCEPTED", "partial close preview passed guards; broker was not mutated", {
            "ticket": position.get("ticket"),
            "close_percent": percent,
            "close_volume": close_volume,
            "remaining_volume": remaining,
            "broker_request_sent": False,
        }

    def _simulate_move_sl_be(
        self,
        action: str,
        payload: dict[str, Any],
        snapshot: dict[str, Any],
        profile: dict[str, Any],
    ) -> tuple[bool, str, str, dict[str, Any] | None]:
        position = self._find_ticket(snapshot.get("positions"), payload.get("ticket"))
        if position is None:
            return False, "POSITION_NOT_FOUND", "target position is not owned/present in latest snapshot", None

        side = str(position.get("side", "")).upper()
        entry = self._positive(position.get("price_open"))
        if side not in {"BUY", "SELL"} or entry is None:
            return False, "POSITION_DATA_INVALID", "position side/open price is unavailable", None

        offset = float(get_path(profile, "management.breakeven_offset_price_units"))
        new_sl = entry + offset if side == "BUY" else entry - offset
        old_sl = self._positive(position.get("sl"))

        if get_path(profile, "safety.never_widen_sl") is True and old_sl is not None:
            if side == "BUY" and new_sl < old_sl - 1e-9:
                return False, "NEVER_WIDEN_SL", "break-even move would widen BUY stop", None
            if side == "SELL" and new_sl > old_sl + 1e-9:
                return False, "NEVER_WIDEN_SL", "break-even move would widen SELL stop", None

        point = self._positive(snapshot.get("point"))
        stops_level = max(0, int(self._number(snapshot.get("stops_level"))))
        bid = self._positive(snapshot.get("bid"))
        ask = self._positive(snapshot.get("ask"))
        if point is not None and stops_level > 0:
            min_distance = stops_level * point
            if side == "BUY" and bid is not None and new_sl > bid - min_distance:
                return False, "BE_TOO_CLOSE_TO_MARKET", "break-even SL violates broker stops level", None
            if side == "SELL" and ask is not None and new_sl < ask + min_distance:
                return False, "BE_TOO_CLOSE_TO_MARKET", "break-even SL violates broker stops level", None

        return True, "SIMULATED_ACCEPTED", "break-even preview passed guards; broker was not mutated", {
            "ticket": position.get("ticket"),
            "side": side,
            "old_sl": old_sl,
            "new_sl": new_sl,
            "broker_request_sent": False,
        }

    def _simulate_start_trailing(
        self,
        action: str,
        payload: dict[str, Any],
        snapshot: dict[str, Any],
        profile: dict[str, Any],
    ) -> tuple[bool, str, str, dict[str, Any] | None]:
        position = self._find_ticket(snapshot.get("positions"), payload.get("ticket"))
        if position is None:
            return False, "POSITION_NOT_FOUND", "target position is not owned/present in latest snapshot", None

        if get_path(profile, "management.trailing_enabled") is not True:
            return False, "TRAILING_DISABLED", "trailing is disabled in the active profile", None

        return True, "SIMULATED_ACCEPTED", "trailing preview passed guards; broker was not mutated", {
            "ticket": position.get("ticket"),
            "mode": get_path(profile, "management.trailing_mode"),
            "step_price_units": get_path(profile, "management.trailing_step_price_units"),
            "broker_request_sent": False,
        }

    def _simulate_modify_pending(
        self,
        action: str,
        payload: dict[str, Any],
        snapshot: dict[str, Any],
        profile: dict[str, Any],
    ) -> tuple[bool, str, str, dict[str, Any] | None]:
        order = self._find_ticket(snapshot.get("orders"), payload.get("ticket"))
        if order is None:
            return False, "ORDER_NOT_FOUND", "target pending order is not owned/present in latest snapshot", None

        changed: dict[str, float] = {}
        for source, target in (("price", "price"), ("sl", "sl"), ("tp", "tp")):
            if source not in payload:
                continue
            value = self._positive(payload.get(source))
            if value is None:
                return False, "ORDER_PRICE_INVALID", f"{source} must be positive", None
            changed[target] = value

        if not changed:
            return False, "NO_CHANGES", "modify pending requires price, sl or tp", None

        return True, "SIMULATED_ACCEPTED", "pending modify preview passed guards; broker was not mutated", {
            "ticket": order.get("ticket"),
            "changes": changed,
            "broker_request_sent": False,
        }

    def _simulate_cancel_pending(
        self,
        action: str,
        payload: dict[str, Any],
        snapshot: dict[str, Any],
        profile: dict[str, Any],
    ) -> tuple[bool, str, str, dict[str, Any] | None]:
        order = self._find_ticket(snapshot.get("orders"), payload.get("ticket"))
        if order is None:
            return False, "ORDER_NOT_FOUND", "target pending order is not owned/present in latest snapshot", None

        return True, "SIMULATED_ACCEPTED", "cancel preview passed guards; broker was not mutated", {
            "ticket": order.get("ticket"),
            "broker_request_sent": False,
        }

    def _simulate_bulk_close(
        self,
        action: str,
        payload: dict[str, Any],
        snapshot: dict[str, Any],
        profile: dict[str, Any],
    ) -> tuple[bool, str, str, dict[str, Any] | None]:
        positions = self._objects(snapshot.get("positions"))
        if action == "CLOSE_PROFIT":
            positions = [p for p in positions if self._number(p.get("profit")) > 0]
        elif action == "CLOSE_LOSS":
            positions = [p for p in positions if self._number(p.get("profit")) < 0]

        if not positions:
            return False, "NO_TARGETS", "no owned positions match the requested bulk action", None

        return True, "SIMULATED_ACCEPTED", "bulk close preview passed guards; broker was not mutated", {
            "tickets": [p.get("ticket") for p in positions],
            "count": len(positions),
            "broker_request_sent": False,
        }

    def _simulate_cancel_all_pending(
        self,
        action: str,
        payload: dict[str, Any],
        snapshot: dict[str, Any],
        profile: dict[str, Any],
    ) -> tuple[bool, str, str, dict[str, Any] | None]:
        orders = self._objects(snapshot.get("orders"))
        if not orders:
            return False, "NO_TARGETS", "no owned pending orders are active", None

        return True, "SIMULATED_ACCEPTED", "bulk cancel preview passed guards; broker was not mutated", {
            "tickets": [o.get("ticket") for o in orders],
            "count": len(orders),
            "broker_request_sent": False,
        }

    def _validate_volume(
        self,
        raw_volume: Any,
        snapshot: dict[str, Any],
        profile: dict[str, Any],
    ) -> tuple[str, str] | None:
        volume = self._positive(raw_volume)
        if volume is None:
            return "VOLUME_INVALID", "volume must be positive"

        minimum = self._positive(snapshot.get("volume_min")) or 0.01
        broker_maximum = self._positive(snapshot.get("volume_max"))
        step = self._positive(snapshot.get("volume_step")) or minimum
        configured_maximum = float(get_path(profile, "risk.max_lot"))

        maximum = min(
            configured_maximum,
            broker_maximum if broker_maximum is not None else configured_maximum,
        )

        if volume < minimum - 1e-9:
            return "VOLUME_BELOW_MIN", "volume is below broker minimum"
        if volume > maximum + 1e-9:
            return "VOLUME_ABOVE_MAX", "volume exceeds active/broker maximum"

        units = volume / step
        if abs(units - round(units)) > 1e-7:
            return "VOLUME_STEP_INVALID", "volume does not align with broker step"

        return None

    @staticmethod
    def _find_ticket(collection: Any, raw_ticket: Any) -> dict[str, Any] | None:
        if isinstance(raw_ticket, bool) or not isinstance(raw_ticket, int):
            return None
        for item in ManualActionSimulator._objects(collection):
            if item.get("ticket") == raw_ticket:
                return item
        return None

    @staticmethod
    def _objects(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _remember(
        self,
        intent_id: str,
        fingerprint: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        self._cache[intent_id] = (fingerprint, deepcopy(result))
        self._cache.move_to_end(intent_id)
        while len(self._cache) > self.MAX_CACHED_INTENTS:
            self._cache.popitem(last=False)
        return result

    @staticmethod
    def _result(
        intent_id: str | None,
        action: str | None,
        accepted: bool,
        code: str,
        message: str,
        preview: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "intent_id": intent_id,
            "action": action,
            "accepted": accepted,
            "code": code,
            "message": message,
            "simulated": True,
            "broker_mutated": False,
            "preview": preview,
            "trading_enabled": False,
            "execution_enabled": False,
        }

    @staticmethod
    def _fingerprint(payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            UUID(value)
            return True
        except (ValueError, TypeError, AttributeError):
            return False

    @staticmethod
    def _number(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0.0
        return float(value)

    @staticmethod
    def _positive(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            return None
        return number
