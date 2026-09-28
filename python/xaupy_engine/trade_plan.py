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


def entry_guard(snapshot: dict, profile: dict, *, reserved_entries: int = 0) -> None:
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


def plan_entry(profile: dict, snapshot: dict, history: dict, side: str, overrides: dict | None = None) -> dict:
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
    entry = ask if buy else bid
    if order_type != side:
        entry = number(overrides.get('price', entry + (1 if buy else -1)*profile['entry']['pending_buffer_price_units']), 'pending_price', positive=True)
        entry = grid(entry, tick, up=buy)
        gap = number(snapshot.get('stops_level'), 'stops_level') * point
        if ((order_type == 'BUY_STOP' and entry < ask+gap) or (order_type == 'SELL_STOP' and entry > bid-gap)
            or (order_type == 'BUY_LIMIT' and entry > ask-gap) or (order_type == 'SELL_LIMIT' and entry < bid+gap)):
            raise TradePlanError('PENDING_PRICE_TOO_CLOSE')
        close_side = entry
    cfg = profile['stop_loss']
    if overrides.get('sl_points') is not None:
        distance = number(overrides['sl_points'], 'sl_points', positive=True) * point
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
        day_budget-=distance/tick*value*number(item.get('volume',item.get('volume_current')),'open_volume',positive=True)
    if day_budget <= 0:
        raise TradePlanError('DAILY_RISK_ALREADY_COMMITTED')
    cash = min(balance*risk['risk_percent']/100, day_budget)
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
                expiration=int(snapshot['server_time'])+profile['entry']['pending_expiration_minutes']*60 if order_type!=side else 0,
                comment=profile['execution']['order_comment'][:31])
