"""Pure broker planning shared by execution and research; never sends an order."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

from .execution_costs import entry_cost_plan
from .strategy_engine import HISTORY_TIMEFRAME_SECONDS, _atr


class TradePlanError(ValueError):
    pass


def number(value: Any, name: str, minimum: float = 0, *, positive: bool = False) -> float:
    if type(value) not in (float, int) or not math.isfinite(value) or value < minimum or (positive and value <= 0):
        raise TradePlanError(f"INVALID_{name.upper()}")
    return float(value)


def grid(value: float, step: float, *, up: bool = False) -> float:
    value, step = number(value, 'price', positive=True), number(step, 'tick_size', positive=True)
    return round((math.ceil(value / step - 1e-9) if up else math.floor(value / step + 1e-9)) * step, 10)


def volume_on_grid(volume: float, snapshot: dict) -> float:
    step = number(snapshot.get('volume_step'), 'volume_step', positive=True)
    result = round(math.floor((volume + 1e-10) / step) * step, 8)
    if result < number(snapshot.get('volume_min'), 'volume_min', positive=True) - 1e-10:
        raise TradePlanError('VOLUME_BELOW_BROKER_MINIMUM')
    if result > number(snapshot.get('volume_max'), 'volume_max', positive=True) + 1e-10:
        raise TradePlanError('VOLUME_ABOVE_BROKER_MAXIMUM')
    return result


def partial_close_volume(volume: float, percent: float, snapshot: dict) -> float:
    """Broker-feasible partial amount, shared by planning and manual execution.

    An impossible partial is a skipped optional management step, not permission
    to round up, close the entire position, or block independent protection.
    """
    volume = number(volume, 'position_volume', positive=True)
    percent = number(percent, 'percent', positive=True)
    if percent >= 100:
        raise TradePlanError('PARTIAL_PERCENT_MUST_BE_BELOW_100')
    amount = volume_on_grid(volume * percent / 100, snapshot)
    minimum = number(snapshot.get('volume_min'), 'volume_min', positive=True)
    if round(volume - amount, 10) < minimum - 1e-9:
        raise TradePlanError('PARTIAL_REMAINDER_BELOW_MINIMUM')
    return amount


def calendar_time(snapshot: dict, sessions: dict) -> datetime:
    stamp = number(snapshot.get('server_time'), 'server_time', positive=True)
    if sessions['timezone'].upper() == 'UTC':
        offset = snapshot.get('server_utc_offset_seconds')
        if type(offset) is not int or abs(offset) > 18 * 3600:
            raise TradePlanError('BROKER_UTC_OFFSET_REQUIRED')
        stamp -= offset
    return datetime.fromtimestamp(stamp, timezone.utc)


def session_allowed(snapshot: dict, sessions: dict) -> bool:
    dt = calendar_time(snapshot, sessions)
    if not sessions[('monday','tuesday','wednesday','thursday','friday','saturday','sunday')[dt.weekday()]]:
        return False
    minute = dt.hour * 60 + dt.minute
    windows = []
    for i in (1, 2):
        if sessions[f'session{i}_enabled']:
            def minutes(text):
                h, m = map(int, text.split(':'))
                return h * 60 + m
            windows.append((minutes(sessions[f'session{i}_start']), minutes(sessions[f'session{i}_end'])))
    return not windows or any(a == b or (a <= minute < b if a < b else minute >= a or minute < b) for a,b in windows)


def weekend_close_due(snapshot: dict, sessions: dict) -> bool:
    if not sessions['weekend_close_enabled']:
        return False
    # Prefer the terminal's actual last Friday trading session when available.
    end = snapshot.get('weekend_session_end')
    now = number(snapshot.get('server_time'), 'server_time', positive=True)
    if type(end) is not int or end <= 0:
        raise TradePlanError('BROKER_WEEKEND_SESSION_REQUIRED')
    return end - sessions['weekend_close_minutes_before'] * 60 <= now <= end


CAPABILITY_FLAGS = ('trade_allowed', 'allow_buy', 'allow_sell', 'market_orders',
                    'stop_orders', 'limit_orders', 'server_sl', 'server_tp',
                    'specified_expiration', 'netting_symbol_exposed')


def broker_capabilities(snapshot: dict, *, required: bool = True) -> dict | None:
    """Snapshot evidence, not an authorization grant; EA repeats every check."""
    value = snapshot.get('execution_capabilities')
    if value is None:
        if required:
            raise TradePlanError('BRIDGE_UPGRADE_REQUIRED')
        return None
    if (not isinstance(value, dict) or type(value.get('schema_version')) is not int
            or value['schema_version'] != 1 or any(type(value.get(k)) is not bool for k in CAPABILITY_FLAGS)):
        raise TradePlanError('BROKER_CAPABILITIES_INVALID')
    return value


def entry_capability_guard(snapshot: dict, *, side: str | None = None, order_type: str | None = None) -> None:
    caps = broker_capabilities(snapshot, required=False)
    if caps is None:
        return  # Research/legacy data has no terminal capabilities; broker service requires them.
    if not caps['trade_allowed']:
        raise TradePlanError('TRADE_PERMISSION_DISABLED')
    if caps['netting_symbol_exposed']:
        raise TradePlanError('NETTING_SYMBOL_ALREADY_EXPOSED')
    if not caps['server_sl']:
        raise TradePlanError('BROKER_SERVER_SL_UNSUPPORTED')
    if (side in ('BUY', 'SELL') and not caps['allow_'+side.lower()]
            or not caps['allow_buy'] and not caps['allow_sell']):
        raise TradePlanError('SYMBOL_ENTRY_DISABLED')
    if order_type:
        if order_type in ('BUY', 'SELL') and not caps['market_orders']:
            raise TradePlanError('BROKER_MARKET_ORDERS_UNSUPPORTED')
        if order_type.endswith('_STOP') and not caps['stop_orders']:
            raise TradePlanError('BROKER_STOP_ORDERS_UNSUPPORTED')
        if order_type.endswith('_LIMIT') and not caps['limit_orders']:
            raise TradePlanError('BROKER_LIMIT_ORDERS_UNSUPPORTED')
        if order_type not in ('BUY', 'SELL') and not caps['specified_expiration']:
            raise TradePlanError('BROKER_EXPIRATION_NOT_SUPPORTED')


def entry_guard(snapshot: dict, profile: dict, *, reserved_entries: int = 0) -> None:
    entry_capability_guard(snapshot)
    if snapshot.get('terminal_connected') is not True:
        raise TradePlanError('TERMINAL_DISCONNECTED')
    if snapshot.get('symbol') != profile['strategy']['symbol'] or snapshot.get('magic') != profile['execution']['magic']:
        raise TradePlanError('PROFILE_BRIDGE_IDENTITY_MISMATCH')
    if not session_allowed(snapshot, profile['sessions']):
        raise TradePlanError('SESSION_BLOCKED')
    if weekend_close_due(snapshot, profile['sessions']):
        raise TradePlanError('WEEKEND_CLOSE_WINDOW')
    risk = profile['risk']
    guard = snapshot.get('demo_once_guard') or snapshot.get('risk_guard') or {}
    if guard.get('history_complete') is not True:
        raise TradePlanError('BROKER_HISTORY_INCOMPLETE')
    now = number(snapshot.get('server_time'), 'server_time', positive=True)
    if guard.get('broker_day_start') != int(now) // 86400 * 86400:
        raise TradePlanError('BROKER_DAY_HISTORY_REQUIRED')
    exposure = len(snapshot.get('positions', [])) + len(snapshot.get('orders', [])) + reserved_entries
    if exposure >= risk['max_open_positions']:
        raise TradePlanError('MAX_OPEN_POSITIONS')
    if number(guard.get('trades_today'), 'trades_today') + reserved_entries >= risk['max_trades_per_day']:
        raise TradePlanError('MAX_TRADES_PER_DAY')
    if number(guard.get('consecutive_losses'), 'consecutive_losses') >= risk['max_consecutive_losses']:
        raise TradePlanError('MAX_CONSECUTIVE_LOSSES')
    realized = number(guard.get('daily_realized'), 'daily_realized', -math.inf)
    day_balance = number(guard.get('day_start_balance'), 'day_start_balance', positive=True)
    if realized <= -day_balance * risk['max_daily_loss_pct'] / 100:
        raise TradePlanError('DAILY_LOSS_LIMIT')
    if risk['stop_after_daily_target'] and realized >= day_balance * risk['daily_target_pct'] / 100:
        raise TradePlanError('DAILY_TARGET_REACHED')
    last_exit = number(guard.get('last_exit_time'), 'last_exit_time')
    if last_exit > now or (last_exit and now-last_exit < risk['cooldown_minutes']*60):
        raise TradePlanError('COOLDOWN')
    if profile['news']['enabled']:
        calendar = snapshot.get('calendar') or {}
        if calendar.get('available') is not True or now-number(calendar.get('as_of'), 'calendar_time') > 300:
            raise TradePlanError('NEWS_CALENDAR_UNAVAILABLE')
        for event in calendar.get('events', []):
            if profile['news']['high_impact_only'] and event.get('importance') != 'HIGH':
                continue
            event_time = number(event.get('time'), 'event_time', positive=True)
            if event_time-profile['news']['minutes_before']*60 <= now <= event_time+profile['news']['minutes_after']*60:
                raise TradePlanError('NEWS_WINDOW')


def closed_history(history: dict, timeframe: str, now: int, count: int) -> list:
    span = HISTORY_TIMEFRAME_SECONDS[timeframe]
    bars = [b for b in history.get(timeframe, []) if b.time + span <= now]
    if len(bars) < count:
        raise TradePlanError('STOP_HISTORY_WARMUP')
    # At a session gap the last candle may be older; reject stale rather than
    # silently price a new order using an unrelated period's volatility.
    if bars[-1].time != (now // span - 1) * span:
        raise TradePlanError('STOP_HISTORY_STALE')
    return bars


def plan_entry(profile: dict, snapshot: dict, history: dict, side: str, overrides: dict | None = None, *, signal: dict | None = None) -> dict:
    overrides = overrides or {}
    if side not in {'BUY','SELL'} or not profile['strategy'][f'allow_{side.lower()}']:
        raise TradePlanError('SIDE_DISABLED')
    buy = side == 'BUY'
    point = number(snapshot.get('point'), 'point', positive=True)
    tick = number(snapshot.get('tick_size'), 'tick_size', positive=True)
    value = number(snapshot.get('tick_value_loss', snapshot.get('tick_value')), 'tick_value_loss', positive=True)
    ask = number(snapshot.get('ask'), 'ask', positive=True)
    bid = number(snapshot.get('bid'), 'bid', positive=True)
    if ask < bid:
        raise TradePlanError('INVALID_SPREAD')
    spread, close_side = ask-bid, bid if buy else ask
    order_type = overrides.get('order_type', side + '_STOP' if profile['entry']['mode'] == 'STOP_CONFIRM' else side)
    if order_type not in {side, side+'_STOP', side+'_LIMIT'}:
        raise TradePlanError('INVALID_ORDER_TYPE')
    entry_capability_guard(snapshot, side=side, order_type=order_type)
    entry = ask if buy else bid
    expiration = 0
    signal_bar_time = None
    if order_type != side:
        expiration = int(snapshot['server_time']) + profile['entry']['pending_expiration_minutes']*60
        pending_price = overrides.get('price')
        if pending_price is None:
            if order_type not in {'BUY_STOP','SELL_STOP'}:
                raise TradePlanError('PENDING_PRICE_REQUIRED')
            tf = profile['timeframes']['trigger']
            span = HISTORY_TIMEFRAME_SECONDS[tf]
            signal_time = (signal or {}).get('bar_time')
            signal_bar = (signal or {}).get('trigger_bar')
            if signal_bar is not None:
                from .strategy_engine import Bar, StrategyDataError
                try:
                    candle = Bar.from_payload(signal_bar)
                except (ValueError, TypeError, StrategyDataError):
                    raise TradePlanError('STOP_CONFIRM_SIGNAL_BAR_REQUIRED')
                if candle.time != signal_time:
                    raise TradePlanError('STOP_CONFIRM_SIGNAL_BAR_REQUIRED')
            else:
                candles = [b for b in history.get(tf, []) if b.time+span <= snapshot['server_time']
                           and (signal_time is None or b.time == signal_time)]
                if not candles:
                    raise TradePlanError('STOP_CONFIRM_SIGNAL_BAR_REQUIRED')
                candle = candles[-1]
            signal_bar_time = candle.time
            observed_at = (signal or {}).get('tick_time_msc')
            created = observed_at//1000 if type(observed_at) is int and observed_at > 0 else candle.time+span
            if created > snapshot['server_time']+1 or created+profile['entry']['max_signal_age_bars']*span <= snapshot['server_time']:
                raise TradePlanError('SIGNAL_EXPIRED')
            expiration = min(created+profile['entry']['pending_expiration_minutes']*60,
                             created+profile['entry']['max_signal_age_bars']*span)
            pending_price = (candle.high+spread+profile['entry']['pending_buffer_price_units'] if buy
                             else candle.low-profile['entry']['pending_buffer_price_units'])
        entry = number(pending_price, 'pending_price', positive=True)
        entry = grid(entry, tick, up=buy)
        gap = number(snapshot.get('stops_level'), 'stops_level') * point
        if ((order_type == 'BUY_STOP' and entry < ask+gap) or (order_type == 'SELL_STOP' and entry > bid-gap)
            or (order_type == 'BUY_LIMIT' and entry > ask-gap) or (order_type == 'SELL_LIMIT' and entry < bid+gap)):
            raise TradePlanError('PENDING_PRICE_TOO_CLOSE')
        close_side = entry
    cfg = profile['stop_loss']
    if overrides.get('sl_points') is not None:
        distance = number(overrides['sl_points'], 'sl_points', positive=True) * point
        if distance < cfg['min_price_units']-1e-9 or distance > cfg['max_price_units']+1e-9:
            raise TradePlanError('EXPLICIT_SL_OUTSIDE_LIMITS')
    elif cfg['mode'] == 'FIXED':
        distance = cfg['fixed_price_units']
    else:
        tf = cfg['structure_timeframe' if cfg['mode']=='STRUCTURE' else 'atr_timeframe']
        count = cfg['structure_lookback'] if cfg['mode']=='STRUCTURE' else cfg['atr_period']+1
        bars = closed_history(history, tf, int(snapshot['server_time']), count)
        if cfg['mode'] == 'STRUCTURE':
            raw = (min(b.low for b in bars[-count:])-cfg['structure_buffer_price_units'] if buy
                   else max(b.high for b in bars[-count:])+cfg['structure_buffer_price_units']+spread)
            distance = entry-raw if buy else raw-entry
        else:
            atr = _atr(bars, cfg['atr_period'])
            if atr is None:
                raise TradePlanError('ATR_WARMUP')
            distance = atr * cfg['atr_multiplier']
    distance = max(cfg['min_price_units'], min(cfg['max_price_units'], distance))
    sl = grid(entry-distance if buy else entry+distance, tick, up=not buy)
    risk_distance = abs(entry-sl)
    tp_cfg = profile['take_profit']
    reward = (number(overrides['tp_points'], 'tp_points', positive=True)*point if overrides.get('tp_points') is not None
              else risk_distance*tp_cfg['rr_ratio'] if tp_cfg['mode']=='RR' else tp_cfg['fixed_price_units'])
    original_tp = grid(entry+reward if buy else entry-reward, tick, up=not buy)
    tp = original_tp
    if tp_cfg['mode'] == 'ZRSI_DYNAMIC':
        emergency = tp_cfg['dynamic']
        tp = (grid(entry+(1 if buy else -1)*max(reward, emergency['emergency_server_tp_price_units']), tick, up=not buy)
              if emergency['emergency_server_tp_enabled'] else 0.0)
    caps = broker_capabilities(snapshot, required=False)
    if tp and caps is not None and not caps['server_tp']:
        raise TradePlanError('BROKER_SERVER_TP_UNSUPPORTED')
    stop_gap = close_side-sl if buy else sl-close_side
    if stop_gap <= 0 or stop_gap+1e-10 < number(snapshot.get('stops_level'), 'stops_level')*point or risk_distance > cfg['max_price_units']+1e-9:
        raise TradePlanError('INVALID_SERVER_STOPS')
    if tp and ((tp-close_side if buy else close_side-tp) <= 0 or abs(tp-close_side)+1e-10 < snapshot['stops_level']*point):
        raise TradePlanError('INVALID_SERVER_TP')
    costs = entry_cost_plan(profile, risk_distance=risk_distance, target_distance=abs(original_tp-entry), spread_price=spread, point=point, tick_size=tick, tick_value=value)
    if costs.blocker:
        raise TradePlanError(costs.blocker)
    risk = profile['risk']
    balance = number(snapshot.get('balance'), 'balance', positive=True)
    guard = snapshot.get('demo_once_guard') or snapshot.get('risk_guard') or {}
    day_budget = number(guard.get('day_start_balance'), 'day_start_balance', positive=True)*risk['max_daily_loss_pct']/100 + min(number(guard.get('daily_realized'), 'daily_realized', -math.inf),0)
    for item in snapshot.get('positions',[]) + snapshot.get('orders',[]):
        existing_sl=number(item.get('sl'),'open_position_sl',positive=True)
        entry_price=number(item.get('price_open'),'open_position_price',positive=True)
        existing_buy=item.get('side',item.get('type','')).startswith('BUY')
        distance=max(0,(entry_price-existing_sl) if existing_buy else (existing_sl-entry_price))
        day_budget-=(distance/tick*value+profile['costs']['max_commission_per_lot'])*number(item.get('volume',item.get('volume_current')),'open_volume',positive=True)
    if day_budget <= 0:
        raise TradePlanError('DAILY_RISK_ALREADY_COMMITTED')
    # Inactive percentage sizing must not secretly cap FIXED_LOT profiles.
    # Both modes still respect the daily risk budget and broker/EA lot limits.
    cash = min(balance*risk['risk_percent']/100, day_budget) if risk['sizing_mode']=='RISK_PERCENT' else day_budget
    cap = min(risk['max_lot'], number(snapshot.get('volume_max'), 'volume_max', positive=True))
    ea_cap = (snapshot.get('guardian') or {}).get('max_volume')
    if ea_cap is not None:
        cap = min(cap, number(ea_cap, 'ea_max_volume', positive=True))
    requested = (number(overrides['volume'], 'volume', positive=True) if overrides.get('volume') is not None
                 else cash/costs.loss_per_lot if risk['sizing_mode']=='RISK_PERCENT' else risk['fixed_lot'])
    volume = volume_on_grid(min(requested, cap), snapshot)
    if overrides.get('volume') is not None and abs(volume-requested)>1e-9:
        raise TradePlanError('REQUESTED_VOLUME_NOT_ALLOWED')
    if volume*costs.loss_per_lot > cash+1e-9:
        raise TradePlanError('RISK_BUDGET_EXCEEDED')
    return dict(action='ENTRY', side=side, order_type=order_type, volume=volume, price=entry, sl=sl, tp=tp,
                original_tp=original_tp, initial_risk=risk_distance, max_loss_money=cash,
                max_deviation_points=profile['costs']['max_slippage_points'],
                max_spread_price_units=profile['costs']['max_spread_price_units'],
                max_commission_per_lot=profile['costs']['max_commission_per_lot'],
                expiration=expiration, signal_bar_time=signal_bar_time,
                comment=profile['execution']['order_comment'][:31])


def pending_cancellation_reason(profile: dict, snapshot: dict, status: dict, side: str, expiration: int = 0) -> str | None:
    """Shared live/replay policy; manual mode callers opt out before invoking it."""
    if expiration > 0 and snapshot['server_time'] >= expiration:
        return 'PENDING_EXPIRED'
    if not session_allowed(snapshot, profile['sessions']):
        return 'PENDING_SESSION_END'
    if weekend_close_due(snapshot, profile['sessions']):
        return 'WEEKEND_CLOSE'
    armed = status.get('armed_side')
    if profile['entry']['cancel_on_opposite_setup'] and armed in {'BUY','SELL'} and armed != side:
        return 'PENDING_OPPOSITE_SETUP'
    direction = status.get('direction')
    if profile['entry']['cancel_on_direction_change'] and direction is not None and direction not in {side,'BOTH'}:
        return 'PENDING_DIRECTION_CHANGED'
    return None
